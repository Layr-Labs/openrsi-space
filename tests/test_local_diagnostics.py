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
            self.assertEqual(report['agent_exit_code'], 1)
            self.assertFalse(report['local_evidence_precheck_passed'])
            self.assertIn('readonly_workspace', [d['code'] for d in report['diagnostics']])
            self.assertNotIn('secret-synthetic-value', json.dumps(report))

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
