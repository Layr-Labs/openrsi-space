"""Managed runtime uses real Git fixtures; no Docker, credentials or inference."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from openrsi_space.common import OpenRSIError
from openrsi_space.integrations.dungeness import managed_runtime as managed


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


class ManagedRuntimeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        git(self.source, 'init', '--quiet')
        (self.source / 'dungeness').write_text('#!/bin/sh\nexit 0\n')
        self.revision = self.commit()
        for context in (patch.object(managed, 'REPOSITORY', str(self.source)),
                        patch.object(managed, 'REVISION', self.revision),
                        patch.dict(os.environ, {'XDG_CACHE_HOME': str(self.root / 'cache')})):
            context.start()
            self.addCleanup(context.stop)

    def commit(self):
        git(self.source, 'add', '.')
        git(self.source, '-c', 'commit.gpgsign=false', '-c', 'user.name=Fixture',
            '-c', 'user.email=fixture@example.invalid', 'commit', '--quiet', '-m', 'fixture')
        return git(self.source, 'rev-parse', 'HEAD')

    def test_fetches_exact_pin_not_repository_tip_then_reuses_offline(self):
        (self.source / 'newer').write_text('not in the pinned release')
        self.commit()
        target = managed.resolve()
        self.assertEqual(git(target, 'rev-parse', 'HEAD'), self.revision)
        self.assertFalse((target / 'newer').exists())
        shutil.rmtree(self.source)
        self.assertEqual(managed.resolve(), target)
        self.assertEqual(git(target, 'status', '--porcelain'), '')

    def test_new_pin_keeps_previous_revision(self):
        old = managed.resolve()
        (self.source / 'newer').write_text('new release')
        revision = self.commit()
        with patch.object(managed, 'REVISION', revision):
            new = managed.resolve()
        self.assertNotEqual(old, new)
        self.assertEqual(git(old, 'rev-parse', 'HEAD'), self.revision)
        self.assertEqual(git(new, 'rev-parse', 'HEAD'), revision)

    def test_override_never_touches_cache_or_network(self):
        with patch.object(managed, '_git', side_effect=AssertionError('managed Git called')):
            self.assertEqual(managed.resolve(self.source), self.source)
        self.assertFalse((self.root / 'cache').exists())

    def test_modified_cache_is_rejected_without_overwriting_it(self):
        target = managed.resolve()
        (target / 'dungeness').write_text('user edit')
        with self.assertRaisesRegex(OpenRSIError, 'incomplete or modified'):
            managed.resolve()
        self.assertEqual((target / 'dungeness').read_text(), 'user edit')

    def test_wrong_revision_is_rejected(self):
        target = managed.resolve()
        with patch.object(managed, '_git', return_value='0' * 40):
            with self.assertRaisesRegex(OpenRSIError, 'incomplete or modified'):
                managed.resolve()
        self.assertEqual(git(target, 'rev-parse', 'HEAD'), self.revision)

    def test_interrupted_fetch_is_not_published_and_can_retry(self):
        original = managed._git
        def interrupted(root, *args):
            if args[0] == 'fetch':
                raise KeyboardInterrupt()
            return original(root, *args)
        with patch.object(managed, '_git', side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                managed.resolve()
        parent = self.root / 'cache/openrsi-space/runtimes/dungeness'
        self.assertFalse((parent / self.revision).exists())
        self.assertEqual(list(parent.glob('.download-*')), [])
        self.assertTrue(managed.resolve().is_dir())

    def test_failed_fetch_does_not_fall_back_to_old_pin(self):
        old = managed.resolve()
        with patch.object(managed, 'REVISION', 'f' * 40):
            with self.assertRaisesRegex(OpenRSIError, 'Cannot prepare managed Dungeness'):
                managed.resolve()
        self.assertTrue(old.is_dir())

    def test_concurrent_preparations_install_once(self):
        original = managed._git
        fetched = []
        def count_fetch(root, *args):
            if args[0] == 'fetch':
                fetched.append(root)
            return original(root, *args)
        with patch.object(managed, '_git', side_effect=count_fetch):
            with ThreadPoolExecutor(max_workers=2) as pool:
                targets = list(pool.map(lambda _: managed.resolve(), range(2)))
        self.assertEqual(targets[0], targets[1])
        self.assertEqual(len(fetched), 1)

    def test_git_failure_is_actionable_without_echoing_credentials(self):
        failure = subprocess.CompletedProcess([], 1, '', 'https://secret@example.invalid')
        with patch.object(managed.subprocess, 'run', return_value=failure):
            with self.assertRaises(OpenRSIError) as caught:
                managed.resolve()
        self.assertIn('--dungeness PATH', str(caught.exception))
        self.assertNotIn('secret', str(caught.exception))
