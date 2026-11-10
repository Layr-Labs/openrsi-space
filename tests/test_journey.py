import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from openrsi_space.cli import main
from openrsi_space.common import write_json
from openrsi_space.contracts.results import PROTOCOL, digest
from openrsi_space.journey import status


class JourneyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / '.openrsi'

    def local(self, **fields):
        path = self.state / 'local/local-one/run.json'
        write_json(path, {'status': 'running', **fields})
        return path

    def test_fresh_workspace_needs_no_login_and_writes_nothing(self):
        with patch('openrsi_space.client.transport.solver_fetch', side_effect=AssertionError('network')):
            result = status(self.state)
        self.assertEqual(result['availability'], 'no_records')
        self.assertEqual(result['phase'], 'choose')
        self.assertEqual(result['completed_phases'], [])
        self.assertNotIn('Model credits:', result['card'])
        self.assertFalse(self.state.exists())

    def test_local_preserves_failure_verification_and_evidence_separately(self):
        path = self.local(status='failed', usage={'normalized_usd': 1.73, 'secret': 'canary'},
                          evaluation={'max_model_credits': 2},
                          final_verification={'status': 'valid', 'score': 42},
                          local_evidence_precheck_passed=True,
                          agent_execution={'last_client_status': 'failed'})
        before = path.read_bytes()
        result = status(self.state)
        self.assertEqual(result['phase'], 'readiness')
        self.assertEqual(result['execution'], 'failed')
        self.assertEqual(result['verification'], 'valid')
        self.assertEqual(result['final_score'], 42)
        self.assertEqual(result['evidence_precheck'], 'passed')
        self.assertEqual(result['usage']['normalized_usd'], 1.73)
        self.assertEqual(result['budget_cap'], 2)
        self.assertEqual(result['agent_execution']['last_client_status'], 'failed')
        self.assertNotIn('canary', json.dumps(result))
        self.assertEqual(before, path.read_bytes())

    def test_runtime_summary_is_used_without_claiming_live_process(self):
        record = self.root / 'runtime/record.json'
        write_json(record, {'data': {'status': 'running'}})
        write_json(record.parent / 'usage/summary.json',
                   {'usage': {'model_requests': 3, 'normalized_usd': 0.4},
                    'evaluation': {'best_score': 55, 'submissions_used': 2}})
        self.local(record_path=str(record))
        result = status(self.state)
        self.assertEqual(result['usage']['model_requests'], 3)
        self.assertEqual(result['candidate_evaluations']['best_score'], 55)
        self.assertEqual(result['phase'], 'local')
        self.assertEqual(result['availability'], 'recorded')
        self.assertIn('stale', result['note'])
        self.assertNotEqual(result['verification'], 'valid')
        self.assertIn('Last saved: running', result['card'])
        self.assertNotIn('not_retained', result['card'])
        self.assertNotIn('Accounting:', result['card'])
        self.assertNotIn('○ not confirmed', result['card'])
        self.assertIn('Explain this run.', result['card'])

    def test_prepared_is_not_running_or_authorized(self):
        self.local(status='prepared')
        result = status(self.state)
        self.assertEqual(result['phase'], 'prepare')
        self.assertIn('authorized budget', result['next_action'])
        self.assertEqual(result['usage']['accounting_state'], 'unknown')

    def test_missing_runtime_keeps_available_metadata(self):
        self.local(record_path=str(self.root / 'absent'), usage={'normalized_usd': 0.3})
        result = status(self.state)
        self.assertEqual(result['usage']['normalized_usd'], 0.3)
        self.assertIn('unavailable', result['note'])

    def test_ambiguous_workspace_requires_explicit_selection(self):
        first = self.local()
        write_json(self.state / 'local/local-two/run.json', {'status': 'completed'})
        result = status(self.state)
        self.assertEqual(result['availability'], 'station')
        self.assertIsNone(result['phase'])
        self.assertEqual(status(self.state, local_run=first)['phase'], 'local')

    def test_station_groups_harness_runs_and_links_remote_by_exact_source(self):
        first = self.local(harness={'id': 'paper-explorer', 'version': 'a' * 64})
        write_json(self.state / 'local/local-two/run.json',
                   {'status': 'completed', 'harness': {'id': 'paper-explorer', 'version': 'b' * 64}})
        write_json(self.state / 'local/local-three/run.json',
                   {'status': 'failed', 'harness': {'id': 'simple-loop', 'version': 'c' * 64}})
        identity, folder, live = self.remote_fixture()
        session = json.loads((folder / 'session.json').read_text())
        session['request']['source']['digest'] = 'a' * 64
        session['local_check'] = {'run_id': 'local-one'}
        write_json(folder / 'session.json', session)
        with patch('openrsi_space.client.transport.solver_fetch', side_effect=AssertionError('network')):
            result = status(self.state, station=True)
            opened = status(self.state, harness='paper-explorer')
        self.assertEqual(len(result['harnesses']), 2)
        self.assertIn('MY RESEARCH STATION', result['card'])
        self.assertIn('2 local · 1 remote', result['card'])
        self.assertEqual(len(opened['harness']['runs']), 3)
        remote = next(r for r in opened['harness']['runs'] if r['kind'] == 'remote')
        self.assertEqual(remote['linked_local_run'], 'local-one')
        selected = status(self.state, local_run=first)
        self.assertIn('● Test locally', selected['card'])
        self.assertIn('Harness: paper-explorer', selected['card'])
        self.assertIn('▶ Local local-one', selected['card'])
        self.assertEqual(selected['usage']['accounting_state'], 'unknown')

    def test_remote_source_mismatch_is_not_grouped_by_claimed_local_id(self):
        self.local(harness={'id': 'paper-explorer', 'version': 'a' * 64})
        identity, folder, _ = self.remote_fixture()
        session = json.loads((folder / 'session.json').read_text())
        session['request']['source']['digest'] = 'b' * 64
        session['local_check'] = {'run_id': 'local-one'}
        write_json(folder / 'session.json', session)
        result = status(self.state, station=True)
        self.assertEqual(len(result['harnesses']), 2)
        orphan = next(g for g in result['harnesses'] if g['harness_id'] is None)
        self.assertEqual(orphan['key'], 'source:' + 'b' * 64)
        self.assertIsNone(orphan['runs'][0]['linked_local_run'])
        self.assertEqual(status(self.state, harness=orphan['key'])['availability'], 'station')

    def test_external_run_with_same_basename_does_not_inherit_workspace_harness(self):
        self.local(harness={'id': 'workspace-harness', 'version': 'a' * 64})
        outside = self.root / 'elsewhere/local-one/run.json'
        write_json(outside, {'status': 'completed', 'harness': {'id': 'different-harness', 'version': 'b' * 64}})
        result = status(self.state, local_run=outside)
        self.assertEqual(result['harness_id'], 'different-harness')
        self.assertNotIn('harness', result)

    def test_run_list_is_bounded_but_json_retains_all_runs(self):
        for i in range(8):
            write_json(self.state / f'local/local-{i}/run.json',
                       {'status': 'completed', 'harness': {'id': 'one-harness', 'version': 'a' * 64}})
        result = status(self.state, local_run=self.state / 'local/local-0')
        self.assertEqual(len(result['harness']['runs']), 8)
        self.assertIn('3 other runs', result['card'])
        self.assertIn('▶ Local local-0', result['card'])

    def test_station_reports_unreadable_records_and_needs_no_login(self):
        self.local().write_text('{')
        with patch('openrsi_space.client.transport.solver_token', side_effect=AssertionError('login')):
            result = status(self.state, station=True)
        self.assertEqual(result['omitted_records'], 1)
        self.assertIn('unreadable', result['card'])

    def test_station_cli_and_unknown_harness(self):
        self.local(harness={'id': 'paper-explorer', 'version': 'a' * 64})
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(['--state', str(self.state), 'journey', 'list', '--json']), 0)
        self.assertEqual(json.loads(output.getvalue())['harnesses'][0]['harness_id'], 'paper-explorer')
        self.assertEqual(status(self.state, harness='missing')['availability'], 'unavailable')

    def test_invalid_or_missing_records_do_not_leak_content(self):
        path = self.local()
        for value in ('canary', '[]', '{'):
            path.write_text(value)
            result = status(self.state, local_run=path)
            self.assertEqual(result['availability'], 'unavailable')
            self.assertNotIn('canary', json.dumps(result))
        self.assertEqual(status(self.state, local_run=self.root/'absent')['availability'], 'unavailable')

    def test_unknown_usage_and_untrusted_values_are_not_zero_or_echoed(self):
        path = self.local(status='canary', usage={'budget_usd': -1, 'model_requests': True},
                   final_verification={'status': 'canary'}, diagnostics=[{'message': 'canary'}])
        path.write_text(path.read_text().replace('"budget_usd": -1', '"budget_usd": NaN'))
        result = status(self.state)
        self.assertNotIn('canary', json.dumps(result))
        self.assertNotIn('budget_usd', result['usage'])
        self.assertNotIn('model_requests', result['usage'])
        self.assertIn('unknown', result['card'])

    def remote_fixture(self):
        identity = 'f46fa5f6-b4b8-4c23-9711-baa08eb90023'
        request = {'request_id': identity, 'source': {'digest': 'source'},
                   'evaluation': {'max_model_credits': 2}, 'problem_set': [],
                   'judge': {'policies': {}}, 'pricing': {}}
        folder = self.state / 'remote/evaluations' / identity
        write_json(folder / 'session.json', {'base': 'https://example.com', 'request': request})
        live = {'protocol': PROTOCOL, 'evaluation_id': identity, 'request_id': identity,
                'source_digest': 'source', 'evaluation_config_digest': digest(request['evaluation']),
                'problem_set_digest': digest([]), 'policies_digest': digest({}), 'pricing_digest': digest({}),
                'status': 'running', 'progress': {'usage': {'budget_usd': 0.7},
                    'evaluation': {'completed': 2, 'best_performance': 50}}}
        return identity, folder, live

    def remote_status(self, live, **kwargs):
        with patch('openrsi_space.client.transport.endpoint', return_value='https://example.com'), \
             patch('openrsi_space.client.transport.solver_token', return_value='private-canary'), \
             patch('openrsi_space.client.transport.solver_fetch', return_value=json.dumps(live)) as fetch:
            result = status(self.state, **kwargs)
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(len(fetch.call_args.args), 3)
            self.assertFalse(fetch.call_args.kwargs)  # GET only, no mutation document
        return result

    def test_remote_live_progress_is_bound_and_read_only(self):
        identity, folder, live = self.remote_fixture()
        before = {p: p.read_bytes() for p in self.state.rglob('*') if p.is_file()}
        result = self.remote_status(live)
        self.assertEqual(result['phase'], 'remote')
        self.assertEqual(result['usage']['budget_usd'], 0.7)
        self.assertEqual(result['candidate_evaluations']['best_score'], 50)
        self.assertEqual(result['verification'], 'unknown')
        self.assertEqual(result['evaluation_id'], identity)
        self.assertNotIn('private-canary', json.dumps(result))
        self.assertEqual(before, {p: p.read_bytes() for p in self.state.rglob('*') if p.is_file()})

    def test_remote_terminal_does_not_write_receipt_or_publish(self):
        identity, folder, live = self.remote_fixture()
        for valid in (True, False, None):
            result = self.remote_status({**live, 'status': 'completed', 'valid': valid}, evaluation=identity)
            self.assertEqual(result['phase'], 'results')
            self.assertEqual(result['verification'], 'valid' if valid is True else 'invalid' if valid is False else 'unknown')
        self.assertEqual([p.name for p in folder.iterdir()], ['session.json'])

    def test_wrong_remote_binding_is_not_displayed(self):
        _, _, live = self.remote_fixture()
        result = self.remote_status({**live, 'source_digest': 'wrong'})
        self.assertEqual(result['availability'], 'unavailable')
        self.assertEqual(result['usage'], {})

    def test_network_failure_and_wrong_endpoint_do_not_claim_completion(self):
        self.remote_fixture()
        with patch('openrsi_space.client.transport.endpoint', return_value='https://wrong.example'), \
             patch('openrsi_space.client.transport.solver_token', return_value='private-canary'), \
             patch('openrsi_space.client.transport.solver_fetch', side_effect=OSError('private-canary')) as fetch:
            result = status(self.state)
            fetch.assert_not_called()
        self.assertEqual(result['availability'], 'unavailable')
        with patch('openrsi_space.client.transport.endpoint', return_value='https://example.com'), \
             patch('openrsi_space.client.transport.solver_token', return_value='private-canary'), \
             patch('openrsi_space.client.transport.solver_fetch', side_effect=OSError('private-canary')):
            result = status(self.state)
        self.assertEqual(result['availability'], 'unavailable')
        self.assertNotIn('private-canary', json.dumps(result))

    def test_cli_json_and_bordered_card(self):
        for args in ([], ['--json']):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(['--state', str(self.state), 'journey', 'status', *args])
            self.assertEqual(code, 0)
            text = output.getvalue()
            card = json.loads(text)['card'] if args else text.rstrip('\n')
            lines = card.splitlines()
            self.assertTrue(lines[0].startswith('┌'))
            self.assertTrue(lines[-1].startswith('└'))
            self.assertEqual({len(line) for line in lines}, {40})
            self.assertIn('● Choose an idea', card)
        self.assertFalse(self.state.exists())
