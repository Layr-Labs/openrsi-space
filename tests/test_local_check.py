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
        # These fixtures simulate a solver's local CLI, even when tests run in CI.
        self.enterContext(patch.dict('os.environ', {'GITHUB_ACTIONS': ''}))
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
                'configuration': {'resolved': {'limits': {'max_usd': 50}}, 'sources': {'agent': {'document': {
                    'execution': {'interface': 'dungeness-command-v1'}}}}},
                'execution': {'stats': {'n_completed_trials': 1, 'n_errored_trials': 0}},
                'usage': {'model_requests': 1, 'model_accounting_state': 'settled'},
            },
        }
        self.event = {'run_id': 'local-test', 'kind': 'model.accounting', 'request_id': 'req-1', 'sequence': 3, 'data': {
            'provider': 'openai', 'model': 'gpt-5.6-sol', 'status': 'success',
            'accounting_method': 'gateway', 'total_tokens': 12, 'normalized_usd': 1.73}}

    def save(self):
        write_json(self.path, self.record)
        write_json(self.path.parent / 'run.json', {
            'id': 'local-test', 'status': 'completed', 'exit_code': 0,
            'record_path': str(self.path)})
        (self.path.parent / 'usage').mkdir(exist_ok=True)
        (self.path.parent / 'usage/events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in self.exchanges(self.event)))

    def exchanges(self, accounting):
        base = {k: accounting[k] for k in ('run_id', 'request_id')}
        pair = {k: accounting['data'][k] for k in ('provider', 'model')}
        return [{**base, 'kind': 'model.request', 'sequence': accounting['sequence'] - 2,
                 'data': {**pair, 'request': {'messages': [{'role': 'user', 'content': 'Read the assigned task.'}]}}},
                {**base, 'kind': 'model.response', 'sequence': accounting['sequence'] - 1,
                 'data': {**pair, 'status': 200, 'response': {'content': 'I will inspect the assigned files.'}}},
                accounting]

    def check(self, **kwargs):
        return check_submission(self.state, self.harness, self.body, self.base, **kwargs)

    def test_existing_run_is_found_without_score_or_another_test(self):
        self.save()
        result = self.check()
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['run_id'], 'local-test')
        self.assertNotIn('score', result)

    def test_remote_time_limit_can_differ_and_budget_can_equal_local_cap(self):
        self.save()
        self.body['evaluation']['max_model_credits'] = 50
        self.body['evaluation']['limits'] = {'max_seconds': 10800, 'max_model_tokens': None}
        self.assertEqual(self.check()['status'], 'passed')

    def test_recorded_cap_not_actual_spend_or_remote_config_controls_eligibility(self):
        self.record['data']['configuration']['resolved']['limits']['max_usd'] = 2
        self.event['data']['normalized_usd'] = 1.73
        self.body['evaluation']['max_model_credits'] = 2
        self.save()
        self.assertEqual(self.check()['local_budget_cap_usd'], 2)
        self.body['evaluation']['max_model_credits'] = 2.0000001
        with self.assertRaisesRegex(CatalystError, 'below the requested remote budget'):
            self.check(local_run=self.path)
        self.record['data']['configuration']['resolved']['limits']['max_usd'] = 1
        self.body['evaluation']['max_model_credits'] = 2
        self.save()
        with self.assertRaisesRegex(CatalystError, 'below the requested remote budget'):
            self.check(local_run=self.path)

    def test_missing_or_invalid_recorded_budget_cap_is_actionable(self):
        for cap in [None, True, False, 0, -1, '2', float('nan'), float('inf'), -float('inf'), {}, []]:
            with self.subTest(cap=cap):
                self.record['data']['configuration']['resolved']['limits']['max_usd'] = 50
                self.save()
                self.record['data']['configuration']['resolved']['limits']['max_usd'] = cap
                self.path.write_text(json.dumps(self.record))
                with self.assertRaisesRegex(CatalystError, 'valid positive finite budget cap'):
                    self.check(local_run=self.path)
        del self.record['data']['configuration']['resolved']
        self.save()
        with self.assertRaisesRegex(CatalystError, 'recorded cap'):
            self.check(local_run=self.path)

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
        with self.assertRaisesRegex(CatalystError, 'cannot be skipped'):
            self.check()
        self.save()
        original = deepcopy(self.record)
        for status in ['prepared', 'running']:
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

    def test_failed_save_preserves_failure_but_complete_evidence_qualifies(self):
        self.record['data']['status'] = 'failed'
        self.record['data']['execution']['stats']['n_errored_trials'] = 1
        self.record['data']['configuration']['repository'] = {'commit': '1'*40}
        self.save()
        metadata = self.path.parent/'run.json'
        doc = json.loads(metadata.read_text())
        doc.update(status='failed', exit_code=1)
        write_json(metadata, doc)
        original = {p: p.read_bytes() for p in (metadata, self.path, self.path.parent/'usage/events.jsonl')}
        decision = self.check(local_run=metadata)
        self.assertEqual(decision['local_run_status'], 'failed')
        self.assertEqual(decision['local_run_path'], str(metadata))
        from catalyst.client.local_evidence import bundle
        self.assertEqual(bundle(metadata, self.body)['status'], 'failed')
        from catalyst.integrations.dungeness.diagnostics import summarize
        diagnostic = summarize(self.path)
        self.assertEqual(diagnostic['record_status'], 'failed')
        self.assertTrue(diagnostic['local_evidence_precheck_passed'])
        self.assertIn('failed_run_evidence_available', [d['code'] for d in diagnostic['diagnostics']])
        self.assertEqual(original, {p: p.read_bytes() for p in original})

    def test_outer_save_failure_is_preserved_through_upload(self):
        from catalyst.client.local_evidence import attach
        from unittest.mock import Mock
        self.record['data']['configuration']['repository'] = {'commit': '1'*40}
        self.save()
        metadata = self.path.parent/'run.json'
        doc = json.loads(metadata.read_text()); doc.update(status='failed', exit_code=1)
        write_json(metadata, doc)
        check = self.check(local_run=metadata)
        def upload(*args, document, **kwargs):
            self.assertEqual(document['status'], 'failed')
            return json.dumps({'protocol':document['protocol'], 'digest':digest(document),'private':True})
        with patch('catalyst.client.transport.solver_fetch', side_effect=upload):
            attach(Mock(), self.body, check)

    def test_partial_duplicate_missing_or_mismatched_exchanges_block_before_upload(self):
        self.record['data']['status'] = 'failed'
        for kind in ('missing_response', 'missing_accounting', 'duplicate', 'truncated', 'count', 'wrong_model'):
            self.save()
            events = self.exchanges(self.event)
            if kind == 'missing_response': events.pop(1)
            if kind == 'missing_accounting': events.pop()
            if kind == 'duplicate': events.append(deepcopy(events[-1]))
            if kind == 'wrong_model': events[1]['data']['model'] = 'wrong-model'
            if kind == 'count':
                self.record['data']['usage']['model_requests'] = 2
                write_json(self.path, self.record)
                self.record['data']['usage']['model_requests'] = 1
            text = ''.join(json.dumps(e)+'\n' for e in events)
            if kind == 'truncated': text += '{'
            (self.path.parent/'usage/events.jsonl').write_text(text)
            with self.subTest(kind=kind), self.assertRaises(CatalystError):
                self.check(local_run=self.path)

    def test_cancelled_ended_run_can_qualify_but_live_trial_cannot(self):
        self.record['data']['status'] = 'cancelled'
        self.record['data']['execution']['stats'].update(n_completed_trials=0,n_cancelled_trials=1)
        self.save()
        self.assertEqual(self.check()['local_run_status'], 'cancelled')
        for field in ('n_running_trials', 'n_pending_trials'):
            self.record['data']['execution']['stats'][field] = 1
            self.save()
            with self.assertRaises(CatalystError): self.check(local_run=self.path)
            self.record['data']['execution']['stats'][field] = 0

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
        event.update(request_id='req-2', sequence=6)
        self.record['data']['usage']['model_requests'] = 2
        self.save()
        with (self.path.parent / 'usage/events.jsonl').open('a') as f:
            f.write(''.join(json.dumps(e)+'\n' for e in self.exchanges(event)))
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

    def test_cli_pass_forwards_completed_local_decision(self):
        self.save()
        parser, _ = build_parser()
        args = parser.parse_args(['remote', 'submit', str(self.harness)])
        with patch('catalyst.client.evaluations.RemoteClient') as factory, \
                patch('catalyst.cli.model_access_input', return_value=None), \
                redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            factory.return_value.base = self.base
            factory.return_value.submit.return_value = {}
            remote_command(args, self.state)
            decision = factory.return_value.submit.call_args.kwargs['local_check']
            self.assertEqual(decision['status'], 'passed')
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

    def test_skip_flag_is_no_longer_accepted(self):
        parser, _ = build_parser()
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(['remote', 'submit', str(self.harness), '--skip-local-check'])
