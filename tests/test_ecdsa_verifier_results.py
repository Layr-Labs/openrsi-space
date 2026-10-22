"""The challenge verifier must publish readable results under restrictive umasks."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from catalyst.problem_assets import ROOT


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / "ecdsa-fail" / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VerifierResultsTests(unittest.TestCase):
    def test_verifier_results_are_readable_after_container_download(self):
        grade = load("command_grade_contract", "verifiers/ecdsa-fail/benchmark-sh/grade.py")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "reward.json"
            prior = os.umask(0o077)
            try:
                grade.atomic_write_json(path, {"ecdsafail_score": 123})
            finally:
                os.umask(prior)
            self.assertEqual(json.loads(path.read_text()), {"ecdsafail_score": 123})
            self.assertEqual(path.stat().st_mode & 0o777, 0o644)

