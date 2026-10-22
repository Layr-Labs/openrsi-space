"""The public challenge owns scaffold assets and installs them as trusted inputs."""
import json
from pathlib import Path
import tempfile
import unittest

from catalyst.common import CatalystError
from catalyst.problem_assets import asset_path, install_assets, registered_assets
from catalyst.problems import get_problem
from catalyst.task_setup import validate_execution, yaml_file


class ProblemAssetsTests(unittest.TestCase):
    def test_scaffold_installed_from_package_without_runtime_copy(self):
        execution = get_problem('ecdsa.fail')['dungeness']
        with tempfile.TemporaryDirectory() as temp:
            runtime = Path(temp)
            manifest = asset_path(runtime, execution['scaffold'])
            self.assertTrue(manifest.is_file())
            self.assertFalse((runtime / execution['scaffold']).exists())
            added = install_assets(runtime, execution)
            self.assertEqual(added, ['scaffolds/ecdsa-point-add-sdk-v1'])
            scaffold = yaml_file(runtime / execution['scaffold'])
            self.assertEqual(scaffold['schema_version'], 2)
            for destination, source in registered_assets().items():
                for file in source.rglob('*'):
                    if file.is_file():
                        self.assertEqual(file.read_bytes(),
                                         (runtime / destination / file.relative_to(source)).read_bytes())
            stub = (runtime / added[0] / 'candidate/mod.rs').read_text()
            self.assertIn('pub fn build() -> Vec<Op>', stub)
            self.assertNotIn('kaliski', stub.lower())
            self.assertNotIn('modular', stub.lower())
            edit = scaffold['text_edits'][1]
            self.assertEqual(edit['path'], 'src/bin/eval_circuit.rs')
            self.assertIn('&[1, 64, 512, NUM_TESTS]', edit['replacement'])
            self.assertIn('std::process::exit(1)', edit['replacement'])

    def test_old_runtime_fails_explicitly_before_assembly(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = Path(temp)
            (runtime / 'runtime-contract.json').write_text(json.dumps({
                'schema_version': 1, 'runtime': 'dungeness', 'capabilities': [],
            }))
            with self.assertRaisesRegex(CatalystError, 'declarative-scaffolds-v2'):
                validate_execution(runtime, runtime, {'execution': get_problem('ecdsa.fail')['dungeness']})
            self.assertFalse((runtime / 'scaffolds').exists())

    def test_unrelated_problem_does_not_install_challenge_assets(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = Path(temp)
            self.assertEqual(install_assets(runtime, {}), [])
            self.assertEqual(list(runtime.iterdir()), [])

    def test_install_refuses_symlink_destination(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime, outside = root / 'runtime', root / 'outside'
            runtime.mkdir()
            outside.mkdir()
            (outside / 'keep.txt').write_text('keep')
            (runtime / 'scaffolds').symlink_to(outside)
            with self.assertRaisesRegex(CatalystError, 'escapes'):
                install_assets(runtime, get_problem('ecdsa.fail')['dungeness'])
            self.assertEqual((outside / 'keep.txt').read_text(), 'keep')
