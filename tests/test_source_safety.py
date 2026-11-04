from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from openrsi_space.common import OpenRSIError, snapshot_directory
from harness_fixture import create_harness


class SourceSafetyTests(unittest.TestCase):
    def test_private_paths_fail_before_reading_their_contents(self):
        for name in ('auth.json','.aws/credentials','.codex/auth.json','.ssh/id_ed25519','token.txt','nested/credentials.json'):
            with self.subTest(path=name),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/'harness';create_harness(root)
                private=root/name;private.parent.mkdir(parents=True,exist_ok=True)
                private.write_text('synthetic-private-value')
                original=Path.read_bytes
                def checked(path):
                    self.assertNotEqual(path,private,'Private content was opened')
                    return original(path)
                with patch.object(Path,'read_bytes',checked),self.assertRaises(OpenRSIError) as error:
                    snapshot_directory(root)
                self.assertIn('outside the harness',str(error.exception))
                self.assertNotIn('synthetic-private-value',str(error.exception))

    def test_clean_harness_and_existing_env_exclusions_still_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'harness';create_harness(root)
            (root/'.env').write_text('PRIVATE=synthetic-value')
            snapshot,bundle=snapshot_directory(root)
            self.assertNotIn('.env',snapshot['files'])
            self.assertIn('agent.py',snapshot['files'])

    def test_error_does_not_echo_arbitrary_parent_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'harness';create_harness(root)
            private=root/'sensitive-parent-canary'/'auth.json';private.parent.mkdir();private.write_text('{}')
            with self.assertRaises(OpenRSIError) as error:snapshot_directory(root)
            self.assertNotIn('sensitive-parent-canary',str(error.exception))
