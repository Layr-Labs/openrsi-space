"""CLI readiness uses retained local evidence, never spends or uploads traces."""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from catalyst.cli import build_parser, remote_command
from catalyst.client.evaluations import RemoteClient, request_body
from catalyst.client.local_check import check_submission, request_identity
from catalyst.common import CatalystError, digest_files, write_json
from catalyst.contracts.results import digest
from catalyst.integrations.dungeness.local import problem_files
from harness_fixture import create_harness


class LocalCheckTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.harness, self.state = self.root / 'harness', self.root / 'state'
        create_harness(self.harness)
        self.base = 'https://verifier.example.test'
        self.body = request_body(self.harness, self.base)
        self.path = self.state / 'local/local-test/record.json'
        self.record = {
            'labels': {'evidence': 'local-development',
                       'catalyst_problem_set_digest': digest(self.body['problem_set'])},
            'data': {
                'run_id': 'local-test', 'status': 'completed',
                'agent': {'package': {'name': 'catalyst-exec-v1',
                                      'version': self.body['source']['digest']}},
                'problem': {'id': 'catalyst-' + digest_files(problem_files(self.body['problem_set'][0]))},
                'model': {'provider': 'openai', 'request_model': 'gpt-5.6-sol'},
                'configuration': {'sources': {'agent': {'document': {
                    'execution': {'interface': 'dungeness-command-v1'}}}}},
                'execution': {'stats': {'n_completed_trials': 1, 'n_errored_trials': 0}},
                'usage': {'model_requests': 1, 'model_accounting_state': 'settled'},
            },
        }
        self.event = {'run_id': 'local-test', 'kind': 'model.accounting', 'data': {
            'provider': 'openai', 'model': 'gpt-5.6-sol', 'status': 'success',
            'accounting_method': 'gateway', 'total_tokens': 12}}

    def save(self):
        write_json(self.path, self.record)
        write_json(self.path.parent / 'run.json', {
            'id': 'local-test', 'status': 'completed', 'exit_code': 0,
            'record_path': str(self.path)})
        (self.path.parent / 'usage').mkdir(exist_ok=True)
        (self.path.parent / 'usage/events.jsonl').write_text(json.dumps(self.event) + '\n')

    def check(self, **kwargs):
        return check_submission(self.state, self.harness, self.body, self.base, **kwargs)

    def test_existing_run_is_found_without_score_or_another_test(self):
        self.save()
        result = self.check()
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['run_id'], 'local-test')
        self.assertNotIn('score', result)

    def test_remote_limits_can_differ_from_local_test(self):
        self.save()
        self.body['evaluation']['max_model_credits'] = 50
        self.body['evaluation']['limits'] = {'max_seconds': 10800, 'max_model_tokens': None}
        self.assertEqual(self.check()['status'], 'passed')

    def test_raw_record_and_older_run_without_new_label_are_supported(self):
        self.record['labels'].pop('catalyst_problem_set_digest')
        self.save()
        for path in [self.path, self.path.parent, self.path.parent / 'run.json']:
            with self.subTest(path=path):
                self.assertEqual(self.check(local_run=path)['status'], 'passed')
        self.record['data']['problem']['id'] = 'catalyst-old-problem'
        self.save()
        with self.assertRaisesRegex(CatalystError, 'problem package differs'):
            self.check(local_run=self.path)

    def test_changed_source_model_reasoning_and_problem_require_retest(self):
        self.save()
        original = deepcopy(self.body)
        changes = [('source', {'digest': 'f' * 64}),
                   ('evaluation', {**original['evaluation'], 'model': {'provider': 'anthropic', 'name': 'claude-opus-5'}}),
                   ('evaluation', {**original['evaluation'], 'model': {**original['evaluation']['model'], 'reasoning_effort': 'high'}}),
                   ('problem_set', [{**original['problem_set'][0], 'title': 'changed'}])]
        for key, value in changes:
            self.body = {**original, key: value}
            with self.subTest(key=key), self.assertRaises(CatalystError):
                self.check()

    def test_missing_prepared_failed_unsettled_and_zero_call_runs_do_not_pass(self):
        with self.assertRaisesRegex(CatalystError, '--skip-local-check'):
            self.check()
        self.save()
        original = deepcopy(self.record)
        for status in ['prepared', 'running', 'failed', 'cancelled']:
            self.record = deepcopy(original)
            self.record['data']['status'] = status
            self.save()
            with self.subTest(status=status), self.assertRaises(CatalystError):
                self.check()
        for usage in [{'model_requests': 0, 'model_accounting_state': 'settled'},
                      {'model_requests': 1, 'model_accounting_state': 'unknown'}]:
            self.record = deepcopy(original)
            self.record['data']['usage'] = usage
            self.save()
            with self.subTest(usage=usage), self.assertRaises(CatalystError):
                self.check()

    def test_provider_errors_and_missing_events_do_not_count_as_model_success(self):
        self.event['data']['status'] = 'provider_error'
        self.save()
        with self.assertRaises(CatalystError):
            self.check()
        (self.path.parent / 'usage/events.jsonl').unlink()
        with self.assertRaises(CatalystError):
            self.check()

    def test_every_model_in_ensemble_needs_successful_accounting(self):
        self.body['evaluation']['models'] = [self.body['evaluation']['model'],
                                            {'provider': 'anthropic', 'name': 'claude-opus-5'}]
        agent = self.record['data']['configuration']['sources']['agent']['document']
        agent['model_access'] = {'models': [self.record['data']['model'],
                                           {'provider': 'anthropic', 'request_model': 'claude-opus-5'}]}
        self.save()
        with self.assertRaises(CatalystError):
            self.check()
        event = deepcopy(self.event)
        event['data'].update(provider='anthropic', model='claude-opus-5')
        with (self.path.parent / 'usage/events.jsonl').open('a') as f:
            f.write(json.dumps(event) + '\n')
        self.assertEqual(self.check()['status'], 'passed')

    def test_broken_records_are_ignored_and_explicit_bad_path_is_actionable(self):
        self.save()
        (self.state / 'local/broken').mkdir()
        (self.state / 'local/broken/run.json').write_text('{')
        self.assertEqual(self.check()['status'], 'passed')
        with self.assertRaisesRegex(CatalystError, 'missing or incomplete'):
            self.check(local_run=self.root / 'missing')

    def test_pending_retry_is_preserved_but_changed_request_is_not_exempt(self):
        name = digest({'base': self.base, 'body': self.body}) + '.json'
        write_json(self.state / 'remote/pending' / name, {**self.body, 'request_id': 'saved-request'})
        self.assertEqual(self.check()['status'], 'resuming')
        self.assertEqual(self.check()['request_id'], 'saved-request')
        self.body['evaluation']['max_model_credits'] += 1
        with self.assertRaises(CatalystError):
            self.check()

    def test_gate_precedes_model_credential_read_and_submit(self):
        parser, _ = build_parser()
        args = parser.parse_args(['remote', 'submit', str(self.harness), '--prompt-model-token'])
        with patch('catalyst.client.evaluations.RemoteClient') as factory, \
                patch('catalyst.cli.model_access_input') as credential, redirect_stderr(io.StringIO()):
            factory.return_value.base = self.base
            with self.assertRaises(CatalystError):
                remote_command(args, self.state)
            credential.assert_not_called()
            factory.return_value.submit.assert_not_called()

    def test_cli_pass_and_explicit_skip_forward_decision_without_trace(self):
        self.save()
        for extra, status in [([], 'passed'), (['--skip-local-check'], 'skipped')]:
            parser, _ = build_parser()
            args = parser.parse_args(['remote', 'submit', str(self.harness), *extra])
            with patch('catalyst.client.evaluations.RemoteClient') as factory, \
                    patch('catalyst.cli.model_access_input', return_value=None), \
                    redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                factory.return_value.base = self.base
                factory.return_value.submit.return_value = {}
                remote_command(args, self.state)
                decision = factory.return_value.submit.call_args.kwargs['local_check']
                self.assertEqual(decision['status'], status)
                self.assertEqual(decision['request_identity'], request_identity(self.body))

    def test_source_change_after_check_fails_before_network(self):
        self.save()
        decision = self.check()
        (self.harness / 'extra.txt').write_text('changed after credential prompt')
        with patch('catalyst.client.transport.endpoint', return_value=self.base):
            client = RemoteClient(self.state, bearer='synthetic')
        with patch('catalyst.client.transport.solver_fetch') as network:
            with self.assertRaisesRegex(CatalystError, 'changed after its local check'):
                client.submit(self.harness, local_check=decision)
            network.assert_not_called()

    def test_decision_stays_local_and_retries_keep_request_id(self):
        self.save()
        decision = self.check()
        with patch('catalyst.client.transport.endpoint', return_value=self.base):
            client = RemoteClient(self.state, bearer='synthetic')
        requests = []
        def accept(base, route, bearer, *, document, **kwargs):
            requests.append(document)
            self.assertNotIn('local_check', document)
            return json.dumps({'evaluation_id': 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee',
                               'request_id': document['request_id']}).encode()
        with patch('catalyst.client.transport.solver_fetch', side_effect=accept):
            accepted = client.submit(self.harness, local_check=decision)
            self.assertEqual(client.session(accepted['evaluation_id'])['local_check']['status'], 'passed')
            self.path.unlink()
            retry = self.check()
            self.assertEqual(retry['status'], 'resuming')
            client.submit(self.harness, local_check=retry)
        self.assertEqual(requests[0]['request_id'], requests[1]['request_id'])
        self.assertEqual(client.session(accepted['evaluation_id'])['local_check']['status'], 'passed')

    def test_check_flags_are_mutually_exclusive(self):
        parser, _ = build_parser()
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(['remote', 'submit', str(self.harness), '--local-run', 'somewhere', '--skip-local-check'])
