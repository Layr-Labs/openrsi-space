"""Trusted problem packages select the workspace independently of submitted code."""
import copy
from pathlib import Path
import tempfile
import unittest

from catalyst.common import CatalystError
from catalyst.challenge.catalog import get_problem
from catalyst.challenge.preparation import execution_initialization, validate_execution, write_yaml


class TaskInitializationTests(unittest.TestCase):
    def test_other_problems_keep_checkpoint_default(self):
        self.assertEqual(execution_initialization({}), {'mode': 'checkpoint'})

    def test_catalyst_default_has_no_initial_solution_or_reference_score(self):
        execution = get_problem('ecdsa.fail')['dungeness']
        self.assertEqual(execution_initialization(execution), {'mode': 'scaffold'})
        self.assertNotIn('reference', execution)

    def test_rejects_untrusted_paths_and_unsupported_initialization(self):
        for execution in (
            {'initialization': {'mode': 'blank'}},
            {'initialization': {'mode': 'scaffold', 'resume_from': 'old'}},
            {'initialization': {'mode': 'scaffold'}},
            {'initialization': {'mode': 'scaffold'}, 'scaffold': '../harness/scaffold.yaml'},
            {'initialization': {'mode': 'scaffold'}, 'scaffold': 'agents/solver/scaffold.yaml'},
            {'scaffold': 'scaffolds/unused.yaml'},
        ):
            with self.subTest(execution=execution), self.assertRaises(CatalystError):
                execution_initialization(execution)

    def test_missing_wrong_and_escaping_scaffolds_fail_before_task_assembly(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime = root / 'runtime'
            execution = copy.deepcopy(get_problem('ecdsa.fail')['dungeness'])
            execution['scaffold'] = 'scaffolds/operator-example/scaffold.yaml'
            manifest = runtime / execution['scaffold']
            with self.assertRaisesRegex(CatalystError, 'does not contain'):
                validate_execution(runtime, root, {'execution': execution})
            write_yaml(manifest, {'schema_version': 1, 'type': 'scaffold', 'candidate_path': 'trusted'})
            with self.assertRaisesRegex(CatalystError, 'candidate path'):
                validate_execution(runtime, root, {'execution': execution})
            manifest.unlink()
            outside = root / 'outside.yaml'
            write_yaml(outside, {'schema_version': 1, 'type': 'scaffold', 'candidate_path': 'src/point_add'})
            manifest.symlink_to(outside)
            with self.assertRaisesRegex(CatalystError, 'escapes'):
                validate_execution(runtime, root, {'execution': execution})
