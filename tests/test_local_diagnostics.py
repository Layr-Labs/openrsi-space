"""Reproduce misleading local success with synthetic Harbor and gateway artifacts."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from catalyst.common import write_json
from catalyst.integrations.dungeness.diagnostics import summarize
from catalyst.contracts.accounting import pricing_schedule, model_prices
from catalyst.contracts.model_equivalence import GROUPS
from catalyst.harnesses import executable


class LocalDiagnosticsTests(unittest.TestCase):
    def test_codex_failure_and_final_verification_are_independent_of_wrapper_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(root/'record.json', {'data': {'status': 'completed',
                'metric': {'name': 'ecdsafail_score'}, 'metrics': {},
                'usage': {'model_requests': 8, 'model_accounting_state': 'settled'}}})
            trial = root/'harbor/run/trial'
            write_json(trial/'agent/harness-outcome.json', {'exit_code': 0})
            (trial/'agent/harness-output-0.txt').write_text('\n'.join(map(json.dumps, [
                {'type': 'turn.failed', 'error': {'message': 'private-canary'}},
                {'event': 'codex_finished', 'exit_code': 1}])))
            write_json(trial/'verifier/score.json', {'status': 'ok', 'score': 37731269540,
                'avg_toffoli': 11313724, 'peak_qubits': 3335, 'stdout_tail': 'private-canary'})
            result = summarize(root/'record.json')
            self.assertEqual(result['agent_execution']['wrapper_exit_code'], 0)
            self.assertEqual(result['agent_execution']['last_client_status'], 'failed')
            self.assertEqual(result['final_verification']['status'], 'valid')
            self.assertEqual(result['metrics']['ecdsafail_score'], 37731269540)
            self.assertFalse(result['local_evidence_precheck_passed'])
            self.assertNotIn('private-canary', json.dumps(result))

    def test_invalid_terminal_score_is_not_a_valid_final_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(root/'record.json', {'data': {'status': 'completed', 'metric': {'name': 'ecdsafail_score'}}})
            write_json(root/'harbor/run/trial/verifier/score.json', {'status': 'invalid', 'score': 1e18})
            result = summarize(root/'record.json')
            self.assertEqual(result['final_verification']['status'], 'invalid')
            self.assertEqual(result['metrics'], {})

    def test_codex_turn_recovery_and_malformed_events(self):
        from catalyst.integrations.dungeness.diagnostics import reported_agent_outcome
        events = [{'type': {}}, {'type': 'turn.failed', 'error': 'private-canary'}, {'type': 'turn.completed'}]
        result = reported_agent_outcome('\n'.join(map(json.dumps, events)))
        self.assertEqual(result['last_client_status'], 'completed')
        self.assertNotIn('private-canary', json.dumps(result))

    def test_nested_failure_is_visible_without_losing_saved_candidate_or_settled_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(root/'record.json', {'data': {'status': 'completed',
                'metric': {'name': 'circuit_score'},
                'usage': {'model_requests': 3, 'model_accounting_state': 'settled'}}})
            write_json(root/'usage/summary.json', {'evaluation': {'submissions_used': 2, 'best_score': 1234}})
            log = root/'harbor/run/trial/agent/harness-output-0.txt'
            log.parent.mkdir(parents=True)
            write_json(log.parent/'harness-outcome.json', {'exit_code': 0})
            log.write_text(json.dumps({'type': 'result', 'is_error': True,
                'terminal_reason': 'api_error', 'api_error_status': 429,
                'error': 'secret-canary'})+'\n'+json.dumps({
                'event': 'stop', 'reason': 'sessions made no metered progress'}))
            report = summarize(root/'record.json')
            self.assertEqual(report['record_status'], 'completed')
            self.assertEqual(report['agent_exit_code'], 0)
            self.assertEqual(report['agent_reported_outcome']['last_client_http_status'], 429)
            self.assertIn('nested_agent_failure', [d['code'] for d in report['diagnostics']])
            self.assertEqual(report['candidate_evaluations']['status'], 'valid_observed')
            self.assertEqual(report['candidate_evaluations']['evaluations'], 2)
            self.assertEqual(report['metrics']['circuit_score'], 1234)
            # A usage total alone is not a retained request/response transcript.
            self.assertFalse(report['local_evidence_precheck_passed'])
            self.assertIn('Actual local spending may be lower', report['local_evidence_note'])
            self.assertNotIn('secret-canary', json.dumps(report))

    def test_recovered_nested_failure_uses_last_result_and_numeric_attempt_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(root/'record.json', {'data': {'status': 'completed'}})
            agent = root/'harbor/run/trial/agent'
            agent.mkdir(parents=True)
            (agent/'harness-output-9.txt').write_text(json.dumps({'type': 'result',
                'is_error': True, 'api_error_status': 429}))
            (agent/'harness-output-10.txt').write_text(json.dumps({'type': 'result',
                'is_error': False, 'terminal_reason': ['untrusted-value']}))
            report = summarize(root/'record.json')
            self.assertEqual(report['agent_reported_outcome']['last_client_status'], 'completed')
            self.assertEqual(report['agent_reported_outcome']['last_client_stop_reason'], 'unspecified')
            self.assertNotIn('last_client_http_status', report['agent_reported_outcome'])
            self.assertNotIn('nested_agent_failure', [d['code'] for d in report['diagnostics']])
            self.assertEqual(report['candidate_evaluations']['status'], 'unknown')

    def test_candidate_validity_does_not_follow_wrapper_success_or_stdout_claims(self):
        for count, expected in [(0, 'not_evaluated'), (2, 'no_valid_observed')]:
            with self.subTest(count=count), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                write_json(root/'record.json', {'data': {'status': 'completed',
                    'evaluation': {'submissions_used': count, 'best_score': None}}})
                log = root/'harbor/run/trial/agent/harness-output-0.txt'
                log.parent.mkdir(parents=True)
                log.write_text('{"score": 1, "valid": true}')
                report = summarize(root/'record.json')
                self.assertEqual(report['candidate_evaluations']['status'], expected)
                self.assertEqual(report['metrics'], {})
                self.assertFalse(report['local_evidence_precheck_passed'])

    def test_legacy_success_does_not_hide_harness_crash_or_secret_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = root/'record.json'
            write_json(record, {'data': {'status': 'completed', 'usage': {'model_requests': 0}}})
            log = root/'harbor/run/trial/exception.txt'
            log.parent.mkdir(parents=True)
            log.write_text('secret-synthetic-value\nRuntimeError: Harness exited with status 1.\nRead-only file system')
            report = summarize(record)
            self.assertEqual(report['record_status'], 'failed')
            self.assertEqual(report['runtime_record_status'], 'completed')
            self.assertEqual(report['agent_exit_code'], 1)
            self.assertFalse(report['local_evidence_precheck_passed'])
            self.assertIn('readonly_workspace', [d['code'] for d in report['diagnostics']])
            self.assertNotIn('secret-synthetic-value', json.dumps(report))

    def test_cross_device_failure_explains_supported_restore_without_echoing_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(root/'record.json', {'data': {'status': 'failed'}})
            log = root/'harbor/run/trial/exception.txt'
            log.parent.mkdir(parents=True)
            log.write_text("OSError: [Errno 18] Invalid cross-device link: "
                           "'/private-synthetic-canary' -> '/other-private-canary'")
            report = summarize(root/'record.json')
            finding = next(d for d in report['diagnostics']
                           if d['code'] == 'workspace_cross_device_operation')
            self.assertIn('copy contents', finding['message'])
            self.assertIn('do not rename the mount root', finding['message'])
            self.assertIn('Snapshot-and-restore harnesses are supported', finding['message'])
            self.assertEqual(report['record_status'], 'failed')
            self.assertNotIn('private-synthetic-canary', json.dumps(report))

    def test_zero_call_success_and_gateway_rejection_are_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(root/'record.json', {'data': {'status': 'completed', 'usage': {'model_requests': 0}}})
            (root/'usage').mkdir()
            (root/'usage/events.jsonl').write_text(json.dumps({'kind': 'gateway.model_request_rejected',
                       'data': {'code': 'output_token_limit', 'maximum': 65536}})+'\n')
            report = summarize(root/'record.json')
            self.assertEqual(report['record_status'], 'completed')
            self.assertFalse(report['local_evidence_precheck_passed'])
            self.assertIn('output_token_limit', [d['code'] for d in report['diagnostics']])

    def test_budget_rejection_reports_safe_amounts_and_does_not_echo_reason(self):
        for retryable in (True, False):
            with self.subTest(retryable=retryable), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); (root/'usage').mkdir()
                write_json(root/'record.json', {'data':{'status':'completed', 'usage':{'model_requests':0}}})
                event={'kind':'gateway.budget_rejected','data':{
                    'code':'model_reservation_exceeds_remaining_budget','upstream_request_sent':False,
                    'retryable':retryable,'available_usd':0.5,'required_reservation_usd':2.74,
                    'reason':'private-synthetic-marker'}}
                (root/'usage/events.jsonl').write_text(json.dumps(event)+'\n')
                report=summarize(root/'record.json'); finding=report['diagnostics'][0]
                self.assertEqual(finding['required_reservation_usd'],2.74)
                self.assertEqual(finding['retryable'],retryable)
                self.assertFalse(report['local_evidence_precheck_passed'])
                self.assertNotIn('private-synthetic-marker',json.dumps(report))

    def test_completed_run_with_pending_usage_has_actionable_diagnostic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            write_json(root/'record.json', {'data':{'status':'completed',
                'usage':{'model_requests':4,'model_accounting_state':'pending'}}})
            report=summarize(root/'record.json')
            self.assertFalse(report['local_evidence_precheck_passed'])
            self.assertIn('model_accounting_unsettled',[d['code'] for d in report['diagnostics']])

    def test_every_advertised_pair_has_unique_pinned_prices(self):
        schedule = pricing_schedule()
        for remote, pairs in GROUPS:
            for provider, name in [('openrouter', remote), *pairs]:
                with self.subTest(provider=provider, model=name):
                    matches = [e for e in schedule['entries'] if e['provider'] == provider and name in e['request_models']]
                    self.assertEqual(len(matches), 1)
                    self.assertGreaterEqual(matches[0]['input_per_mtok'], 0)
                    self.assertGreater(matches[0]['output_per_mtok'], 0)
        opus = model_prices({'provider': 'claude-subscription', 'name': 'claude-opus-5-5'})
        self.assertEqual([opus[k] for k in ('input_per_mtok', 'output_per_mtok', 'cached_read_per_mtok', 'cache_write_per_mtok', 'cache_write_1h_per_mtok')], [4, 20, .2, 5, 8])

    def test_problem_smoke_has_trusted_readonly_overlays_and_deadline(self):
        from catalyst.challenge.catalog import get_problem
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root/'repo'
            workspace.mkdir()
            with patch.object(executable, 'inspect_build', return_value={'image_id':'synthetic','source_digest':'a'*64}), \
                 patch('catalyst.challenge.catalog.validate_workspace'), \
                 patch.object(executable, 'docker_output', return_value='ok') as docker, \
                 patch.object(executable.subprocess, 'run'):
                result = executable.smoke(root/'state', 'build', workspace, problem=get_problem('ecdsa.fail'), timeout=120)
            command = docker.call_args.args[0]
            mounts = [command[i+1] for i,v in enumerate(command) if v == '--mount']
            self.assertTrue(any('target=/workspace/repo/POINT_ADD_SDK.md,readonly' in m for m in mounts))
            self.assertTrue(any('target=/workspace/repo/src/point_add_sdk.rs,readonly' in m for m in mounts))
            task = json.loads((root/'state/smoke'/result['id']/'input/task.json').read_text())
            self.assertEqual(task['remaining_seconds'], 120)
            self.assertEqual(len(task['readonly_workspace_paths']), 2)
            self.assertFalse((workspace/'POINT_ADD_SDK.md').exists())
