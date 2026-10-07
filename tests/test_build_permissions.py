"""A service umask must not make copied harness or launcher code root-readable only."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from catalyst.executable import build

ROOT = Path(__file__).resolve().parents[1]


class BuildPermissionTests(unittest.TestCase):
    def test_restrictive_umask_builds_readable_source_and_launcher_with_new_identity(self):
        contexts = []

        def docker(args, **_):
            if args[0] == "info":
                return "linux/x86_64"
            if args[:2] == ["image", "inspect"]:
                return "sha256:" + "a" * 64
            if args[0] == "build":
                context = Path(args[-1])
                contexts.append(context.name)
                for item in context.rglob("*"):
                    if item.is_file():
                        self.assertEqual(item.stat().st_mode & 0o777, 0o644, str(item))
            return ""

        with tempfile.TemporaryDirectory() as directory, patch("catalyst.executable.docker_output", side_effect=docker):
            previous = os.umask(0o077)
            try:
                result = build(Path(directory), ROOT / "harnesses/ecdsa-baseline")
            finally:
                os.umask(previous)
        self.assertEqual(result["builder_version"], 2)
        self.assertEqual(len(contexts), 2)
