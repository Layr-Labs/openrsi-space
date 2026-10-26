from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path


from catalyst.challenge.assets import ROOT

REPOSITORY_ROOT = ROOT / "ecdsa-fail"
SERVERS = (
    REPOSITORY_ROOT / "verifiers/benchmark-sh/serve.py",
    REPOSITORY_ROOT / "verifiers/experiment-bin/serve.py",
)


def load_server(path: Path, name: str) -> object:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class EvaluatorUsageEventTests(unittest.TestCase):
    def test_fallback_writes_one_canonical_evaluation_event(self) -> None:
        original_grade = sys.modules.get("grade")
        sys.modules["grade"] = types.ModuleType("grade")
        try:
            for index, path in enumerate(SERVERS):
                with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                    module = load_server(path, f"evaluator_server_{index}")
                    usage = Path(directory)
                    usage.chmod(0o777)
                    (usage / "events.jsonl").touch()
                    (usage / "events.jsonl").chmod(0o666)
                    module.USAGE_DIR = usage
                    module.RUN_ID = "test-run"
                    module._submissions = 3
                    module._best_score = 42.0
                    (usage / "summary.json").write_text(
                        json.dumps(
                            {"usage": {"normalized_usd": 1.25}}
                        ),
                        encoding="utf-8",
                    )

                    event = {
                        "event_id": "evaluation:3",
                        "operation": "score",
                        "status": "ok",
                        "score": 42.0,
                        "avg_toffoli": 21,
                        "peak_qubits": 2,
                    }
                    module._record(event)
                    module._record(event)

                    lines = (
                        usage / "events.jsonl"
                    ).read_text(encoding="utf-8").splitlines()
                    self.assertEqual(len(lines), 1)
                    self.assertEqual(usage.stat().st_mode & 0o777, 0o700)
                    self.assertEqual((usage / "events.jsonl").stat().st_mode & 0o777, 0o600)
                    record = json.loads(lines[0])
                    self.assertEqual(record["source"], "evaluator")
                    self.assertEqual(record["kind"], "evaluation.completed")
                    self.assertEqual(record["event_id"], "evaluation:3")
                    self.assertEqual(record["data"]["submissions_used"], 3)
                    self.assertEqual(record["data"]["best_score"], 42.0)
                    self.assertEqual(record["data"]["metrics"], {"avg_toffoli": 21, "peak_qubits": 2})
                    self.assertEqual(record["data"]["avg_toffoli"], 21)
                    self.assertEqual(record["data"]["peak_qubits"], 2)
                    self.assertEqual(record["usage"]["normalized_usd"], 1.25)
                    self.assertFalse((usage / "eval-events.jsonl").exists())
                    self.assertFalse((usage / "eval-summary.json").exists())
        finally:
            if original_grade is None:
                sys.modules.pop("grade", None)
            else:
                sys.modules["grade"] = original_grade


if __name__ == "__main__":
    unittest.main()
