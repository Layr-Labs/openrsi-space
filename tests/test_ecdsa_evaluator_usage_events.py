from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import types
import tarfile
import unittest
from unittest.mock import patch
from pathlib import Path


from openrsi_space.challenge.assets import ROOT

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
    def test_notes_rejected_with_location_then_rust_candidate_can_be_scored(self):
        from unittest.mock import Mock
        grade = types.ModuleType('grade')
        grade.INVALID_SCORE = 1e18
        grade.score_candidate = Mock(return_value={
            'status': 'ok', 'score': 42, 'avg_toffoli': 21, 'peak_qubits': 2})
        with patch.dict(sys.modules, {'grade': grade}):
            module = load_server(SERVERS[0], 'candidate_format_server')
        for name, content, expected in (
            ('memory/notes.md', b'private note text', 'candidate-not-rust'),
            ('bad.rs', b'\xff', 'candidate-not-utf8'),
            (None, None, None),
        ):
            archive = io.BytesIO()
            files = {'mod.rs': b'fn build() {}'}
            if name:
                files[name] = content
            with tarfile.open(fileobj=archive, mode='w') as tar:
                for filename, raw in files.items():
                    member = tarfile.TarInfo(filename)
                    member.size = len(raw)
                    tar.addfile(member, io.BytesIO(raw))
            source = archive.getvalue()
            handler = object.__new__(module.Handler)
            handler.path = '/score'
            handler.headers = {'content-length': str(len(source))}
            handler.rfile = io.BytesIO(source)
            replies = []
            handler._reply = lambda code, body: replies.append((code, body))
            with patch.object(module, '_record') as record:
                handler.do_POST()
            code, body = replies.pop()
            self.assertEqual(code, 200)
            if expected:
                finding = {'path': name, 'rule': expected, 'line': 1}
                self.assertEqual(body['status'], 'screen_rejected')
                self.assertEqual(body['screening_findings'], [finding])
                self.assertEqual(record.call_args.args[0]['screening_findings'], [finding])
                self.assertIn('outside', body['detail'])
                self.assertNotIn('private note text', json.dumps(body))
                grade.score_candidate.assert_not_called()
            else:
                self.assertEqual(body['status'], 'ok')
                grade.score_candidate.assert_called_once()

    def test_invalid_score_response_exposes_bounded_stdout_and_stderr(self) -> None:
        grade = types.ModuleType('grade')
        with patch.dict(sys.modules, {'grade': grade}):
            for index, path in enumerate(SERVERS):
                module = load_server(path, f'diagnostic_server_{index}')
                source = b'// synthetic candidate'
                if path.parent.name == 'benchmark-sh':
                    archive = io.BytesIO()
                    with tarfile.open(fileobj=archive, mode='w') as tar:
                        member = tarfile.TarInfo('mod.rs')
                        member.size = len(source)
                        tar.addfile(member, io.BytesIO(source))
                    source = archive.getvalue()
                for stdout, stderr in (
                    ('!! correctness FAILED: CLASSICAL MISMATCH', ''),
                    ('!! correctness FAILED: PHASE GARBAGE', 'compiler warning'),
                    ('', 'error: failed to compile'),
                    ('x' * 5000 + 'CLASSICAL MISMATCH', 'y' * 5000 + 'compiler error'),
                    ('', ''),
                ):
                    with self.subTest(path=path, stdout=stdout[-60:], stderr=stderr[-60:]):
                        grade.score_candidate = lambda _: {
                            'status': 'invalid', 'score': 1e18,
                            'avg_toffoli': None, 'peak_qubits': None,
                            'stdout_tail': stdout, 'stderr_tail': stderr}
                        handler = object.__new__(module.Handler)
                        handler.path = '/score'
                        handler.headers = {'content-length': str(len(source))}
                        handler.rfile = io.BytesIO(source)
                        replies = []
                        handler._reply = lambda code, body: replies.append((code, body))
                        with patch.object(module, '_record'):
                            handler.do_POST()
                        code, body = replies.pop()
                        self.assertEqual(code, 200)
                        self.assertEqual(body['status'], 'invalid')
                        self.assertEqual(body['score'], 1e18)
                        self.assertTrue(body['detail'])
                        self.assertLessEqual(len(body['detail']), 2020)
                        if stdout:
                            self.assertIn(stdout[-1000:], body['detail'])
                        if stderr:
                            self.assertIn(stderr[-1000:], body['detail'])

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
