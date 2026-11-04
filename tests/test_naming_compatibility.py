"""A branding migration must not orphan local work or rewrite signed identities."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from openrsi_space.compatibility import environment, state_directory, LEGACY_STATE, LEGACY_INTERFACE
from openrsi_space.contracts.harness import validate_execution
from openrsi_space.common import OpenRSIError, snapshot_directory
from openrsi_space.integrations.yukon import receipts
from openrsi_space.runtime import launch


class NamingCompatibilityTests(unittest.TestCase):
    def test_environment_prefers_current_setting_and_accepts_previous_setting(self):
        with patch.dict(os.environ, {'CATALYST_EVALUATOR_URL':'https://previous.invalid'}, clear=True):
            self.assertEqual(environment('OPENRSI_EVALUATOR_URL'), 'https://previous.invalid')
            os.environ['OPENRSI_EVALUATOR_URL'] = 'https://current.invalid'
            self.assertEqual(environment('OPENRSI_EVALUATOR_URL'), 'https://current.invalid')
            os.environ['OPENRSI_EVALUATOR_URL'] = ''
            self.assertEqual(environment('OPENRSI_EVALUATOR_URL'), '')

    def test_default_state_reuses_existing_work_without_moving_it(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            root=Path(directory)
            self.assertEqual(state_directory(root), root/'.openrsi')
            old=root/LEGACY_STATE
            old.mkdir(); (old/'run.json').write_text('retained')
            self.assertEqual(state_directory(root),old)
            (root/'.openrsi').mkdir()
            self.assertEqual(state_directory(root),root/'.openrsi')
            self.assertEqual((old/'run.json').read_text(),'retained')

    def test_both_execution_names_validate_without_modifying_manifest(self):
        for name in ('openrsi-exec-v1',LEGACY_INTERFACE):
            execution={'interface':name,'dockerfile':'Dockerfile','entrypoint':['python3','agent.py']}
            before=json.dumps(execution)
            validate_execution(execution)
            self.assertEqual(json.dumps(execution),before)

    def test_launcher_supports_existing_and_new_harnesses(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);task=root/'task.json';execution=root/'execution.json'
            task.write_text(json.dumps({'workspace':directory,'model':'model'}))
            execution.write_text(json.dumps({'entrypoint':['python3','agent.py']}))
            with patch.object(launch.subprocess,'run') as run:
                run.return_value.returncode=0
                self.assertEqual(launch.launch(task,execution),0)
            env=run.call_args.kwargs['env']
            self.assertEqual(env['OPENRSI_TASK'],env['CATALYST_TASK'])
            self.assertEqual(env['OPENRSI_WORKSPACE'],directory)

    def test_old_pinned_score_location_is_cleared_before_failed_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);relative=f'{LEGACY_STATE}/yukon/score.json'
            (root/'benchmark.json').write_text(json.dumps({'scorePath':relative}))
            target=root/relative;target.parent.mkdir(parents=True);target.write_text('stale')
            with self.assertRaises(OpenRSIError):receipts.check_receipt(root)
            self.assertFalse(target.exists())
