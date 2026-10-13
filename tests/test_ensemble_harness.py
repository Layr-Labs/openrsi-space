import base64
import importlib.util
from pathlib import Path
import unittest

from catalyst.cheat_filter import screen
from catalyst.common import open_bundle
from catalyst.remote import request_body

ROOT = Path(__file__).resolve().parents[1] / "harnesses/ecdsa-ensemble"


class EnsembleHarnessTests(unittest.TestCase):
    def test_source_package_is_a_non_codex_harness_with_two_models(self):
        body = request_body(ROOT, "https://example.invalid")
        _, files = open_bundle(base64.b64decode(body["source"]["archive_base64"]))
        self.assertEqual(screen(files, "harness")["status"], "passed")
        self.assertEqual(len(body["evaluation"]["models"]), 2)
        self.assertIn(b"ProcessPoolExecutor", files["agent.py"])
        self.assertNotIn(b"subprocess.run([\"codex\"", files["agent.py"])

    def test_model_output_cannot_write_outside_candidate_directory(self):
        spec = importlib.util.spec_from_file_location("ensemble", ROOT / "agent.py")
        agent = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(agent)
        self.assertEqual(agent.decode_candidate('{"files":{"mod.rs":"valid"}}'), {"mod.rs": "valid"})
        import json
        for name in ("../mod.rs", "/mod.rs", "a/../../mod.rs", "mod.py", "a\\mod.rs"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                agent.decode_candidate(json.dumps({"files": {"mod.rs": "", name: "bad"}}))
