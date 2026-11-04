"""Agent compiler feedback is independent of authoritative evaluation."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from openrsi_space.runtime import launch


class LocalToolchainTests(unittest.TestCase):
    def test_matching_mismatched_missing_and_timed_out_compiler(self):
        cases = [
            (SimpleNamespace(returncode=0, stdout='rustc 1.93.0 (abc)'), 'available', '1.93.0'),
            (SimpleNamespace(returncode=0, stdout='rustc 1.90.0 (abc)'), 'unavailable', '1.90.0'),
            (FileNotFoundError(), 'unavailable', None),
            (launch.subprocess.TimeoutExpired('rustc', 10), 'unavailable', None),
        ]
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            for filename, pin in [('rust-toolchain', '1.93.0\n'),
                                  ('rust-toolchain.toml', '[toolchain]\nchannel = "1.93.0"\n')]:
                path = workspace / filename
                path.write_text(pin)
                for result, status, observed in cases:
                    with self.subTest(filename=filename, status=status, observed=observed), \
                            patch.object(launch.subprocess, 'run') as run, patch('builtins.print'):
                        if isinstance(result, Exception):
                            run.side_effect = result
                        else:
                            run.return_value = result
                        task = launch.check_local_toolchain({'workspace': directory, 'instruction': 'Research.'})
                        self.assertEqual(task['local_toolchain']['status'], status)
                        self.assertEqual(task['local_toolchain']['observed_version'], observed)
                        self.assertEqual(run.call_args.kwargs['env']['RUSTUP_AUTO_INSTALL'], '0')
                        self.assertEqual(run.call_args.kwargs['env']['RUSTUP_TOOLCHAIN'], '1.93.0')
                        if status == 'unavailable':
                            self.assertIn('Use evaluate', task['instruction'])
                path.unlink()

    def test_missing_compiler_does_not_block_harness_and_is_in_assigned_task(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'rust-toolchain').write_text('1.93.0')
            task = root / 'input.json'
            task.write_text(json.dumps({'workspace': directory}))
            execution = root / 'execution.json'
            execution.write_text(json.dumps({'entrypoint': ['solver']}))
            with patch.object(launch.subprocess, 'run') as run, patch('builtins.print'):
                run.side_effect = [FileNotFoundError(), SimpleNamespace(returncode=0)]
                self.assertEqual(launch.launch(task, execution), 0)
                resolved = json.loads(Path(run.call_args.kwargs['env']['OPENRSI_TASK']).read_text())
                self.assertEqual(resolved['local_toolchain']['status'], 'unavailable')
                self.assertIn('Use evaluate', resolved['instruction'])
                self.assertIn('does not need Rust in the agent container', resolved['instruction'])

    def test_non_rust_harness_needs_no_compiler_probe(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(launch.subprocess, 'run') as run:
            task = {'workspace': directory}
            self.assertIs(launch.check_local_toolchain(task), task)
            run.assert_not_called()
