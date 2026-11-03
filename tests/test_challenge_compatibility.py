"""Existing verifier imports must reach the relocated challenge implementation."""
import importlib
import json
import unittest
from unittest.mock import patch

from catalyst.challenge import catalog
from catalyst.challenge.paths import PROBLEM_SET


class ChallengeCompatibilityTests(unittest.TestCase):
    def test_legacy_imports_share_module_and_configuration(self):
        for old, new in {
            "problems": "catalog", "problem_assets": "assets",
            "paper_library": "papers", "knowledge_base": "resources",
            "task_setup": "preparation",
        }.items():
            with self.subTest(module=old):
                previous = importlib.import_module("catalyst." + old)
                current = importlib.import_module("catalyst.challenge." + new)
                self.assertIs(previous, current)
        with patch("catalyst.paper_library.CATALOGS", {}):
            self.assertEqual(importlib.import_module("catalyst.challenge.papers").CATALOGS, {})
        with patch("catalyst.problem_assets.registered_assets", return_value={}):
            self.assertEqual(importlib.import_module("catalyst.challenge.assets").registered_assets(), {})

    def test_relocated_loader_reads_the_original_problem_set(self):
        for release, name in catalog.PROBLEM_RELEASES.items():
            with self.subTest(release=release):
                self.assertEqual(catalog.initial_problems(release=release),
                                 json.loads((PROBLEM_SET / name).read_text())["problems"])
        self.assertEqual(catalog.problem_statement("ecdsa.fail"),
                         (PROBLEM_SET / "ecdsa-fail/description.md").read_text())
