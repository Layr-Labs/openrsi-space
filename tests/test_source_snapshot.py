"""Deterministic local races use synthetic outside files, never credentials."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from catalyst.common import CatalystError, open_bundle, snapshot_directory
from harness_fixture import create_harness


class SnapshotRaceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)/'harness'
        create_harness(self.root)
        self.outside = Path(tmp.name)/'outside.txt'
        self.outside.write_text('SYNTHETIC-OUTSIDE-CANARY')

    def test_file_swap_between_stat_and_open_fails_without_following_link(self):
        original = os.open
        def raced(name, flags, *args, **kwargs):
            if name == 'agent.py' and kwargs.get('dir_fd') is not None:
                (self.root/'agent.py').unlink()
                (self.root/'agent.py').symlink_to(self.outside)
            return original(name, flags, *args, **kwargs)
        with patch('os.open', raced), self.assertRaises(CatalystError):
            snapshot_directory(self.root)

    def test_parent_directory_swap_is_rejected(self):
        nested = self.root/'nested'
        nested.mkdir()
        (nested/'code.py').write_text('ordinary source')
        original = os.open
        def raced(name, flags, *args, **kwargs):
            if name == 'nested' and kwargs.get('dir_fd') is not None:
                nested.rename(self.root/'old-nested')
                nested.symlink_to(self.outside.parent, target_is_directory=True)
            return original(name, flags, *args, **kwargs)
        with patch('os.open', raced), self.assertRaises(CatalystError):
            snapshot_directory(self.root)

    def test_change_to_open_file_is_detected(self):
        original = os.read
        changed = False
        def raced(fd, amount):
            nonlocal changed
            data = original(fd, amount)
            if data and not changed:
                changed = True
                # Same descriptor, same inode; detect changed content metadata.
                (self.root/'Dockerfile').write_text('changed while capturing')
            return data
        with patch('os.read', raced), self.assertRaises(CatalystError):
            snapshot_directory(self.root)

    def test_fifo_rejected_without_blocking(self):
        os.mkfifo(self.root/'pipe')
        with self.assertRaisesRegex(CatalystError, 'special files'):
            snapshot_directory(self.root)

    def test_uploaded_bytes_are_immutable_after_capture(self):
        snapshot, data = snapshot_directory(self.root)
        (self.root/'agent.py').write_text('later modification')
        recovered, files = open_bundle(data)
        self.assertEqual(recovered, snapshot)
        self.assertNotEqual(files['agent.py'], b'later modification')
