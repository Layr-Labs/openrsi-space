"""Standalone CLI against the real API, including handoff to the Yukon adapter."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from catalyst.cli import main
from catalyst.common import read_json, write_json
from catalyst.remote import RemoteClient, digest, request_body, private_json
from catalyst.worker import run_one
from catalyst.yukon import run_remote
from test_evaluator import EvaluatorFixture
from test_yukon import completed


class RemoteCLITests(EvaluatorFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.state = self.root / "client"
        write_json(self.root / "problem-set.json", self.request["problem_set"])
        self.environment = patch.dict(os.environ, {
            "CATALYST_API_TOKEN": "alice-token", "YUKON_API_TOKEN": "", "GITHUB_ACTIONS": "",
            "YUKON_EVALUATION": "", "CATALYST_LOCAL_TEST": "1",
            "CATALYST_LOCAL_ECDSA": "",
            "CATALYST_LOCAL_PROBLEM_SET": str(self.root / "problem-set.json"),
            "CATALYST_EVALUATOR_URL": f"http://127.0.0.1:{self.server.server_port}",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def cli(self, *args):
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors), patch("catalyst.remote.time.sleep"):
            code = main(["--state", str(self.state), "remote", *map(str, args)])
        return code, json.loads(output.getvalue()) if output.getvalue() else None, errors.getvalue()

    def submit(self):
        code, document, errors = self.cli("submit", self.root / "submission")
        self.assertEqual(code, 0, errors)
        return document["evaluation_id"]

    def finish_worker(self):
        class Backend:
            def evaluate(self, job, folder, transition):
                transition("running")
                transition("verifying")
                return completed(job["request"], job["id"])
        return run_one(self.store, Backend())

    def test_submit_returns_immediately_and_status_does_not_execute_harness(self):
        identity = self.submit()
        self.assertEqual(self.store.get(identity)["status"], "queued")
        self.assertFalse((self.root / "submission/verification.json").exists())
        code, status, errors = self.cli("status", identity)
        self.assertEqual(code, 0, errors)
        self.assertEqual(status["status"], "queued")
        self.assertNotIn("archive_base64", json.dumps(status))
        session_file = self.state / "remote/evaluations" / identity / "session.json"
        self.assertNotIn("alice-token", session_file.read_text())
        self.assertEqual(session_file.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.submit(), identity)

    def test_wait_resumes_with_fresh_client_and_exports_reference_without_new_job(self):
        identity = self.submit()
        self.finish_worker()
        for _ in range(2):
            code, result, errors = self.cli("wait", identity)
            self.assertEqual(code, 0, errors)
            self.assertEqual(result["scores"], [100, .25])
            self.assertEqual(result["evidence_mode"], "local-test")
            self.assertEqual(read_json(Path(result["verification"]))["evaluation_id"], identity)
        code, traces, errors = self.cli("traces", identity)
        self.assertEqual(code, 0, errors)
        self.assertTrue(Path(traces["traces"]).is_file())
        self.assertIsNone(self.store.claim())
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM jobs").fetchone()[0], 1)

    def test_submit_wait_uses_the_previously_accepted_request(self):
        identity = self.submit()
        self.finish_worker()
        code, result, errors = self.cli("submit", self.root / "submission", "--wait")
        self.assertEqual(code, 0, errors)
        self.assertEqual(result["evaluation_id"], identity)
        self.assertEqual(result["status"], "completed")

    def test_yukon_run_picks_up_standalone_submission(self):
        identity = self.submit()
        self.finish_worker()
        with patch("catalyst.yukon.Path.cwd", return_value=self.root), \
                patch("catalyst.remote.time.sleep"), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            artifact = run_remote(self.state)
        self.assertEqual(artifact["metrics"]["evaluationId"], identity)
        self.assertEqual(read_json(self.root / ".catalyst/yukon/score.json"), artifact)
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM jobs").fetchone()[0], 1)

    def test_changed_source_retains_original_result_without_exporting_old_reference(self):
        identity = self.submit()
        self.finish_worker()
        with (self.root / "submission/agent.py").open("a") as file:
            file.write("\n# new work while the remote evaluation finishes\n")
        code, _, errors = self.cli("wait", identity)
        self.assertEqual(code, 1)
        self.assertIn("Submission changed", errors)
        self.assertFalse((self.root / "submission/verification.json").exists())
        self.assertTrue((self.state / "remote/evaluations" / identity / "judgment.json").is_file())

    def test_saved_endpoint_and_identity_are_checked_before_network(self):
        identity = self.submit()
        with patch.dict(os.environ, {"CATALYST_EVALUATOR_URL": "https://different.invalid"}):
            code, _, errors = self.cli("status", identity)
        self.assertEqual(code, 1)
        self.assertIn("endpoint differs", errors)
        code, _, errors = self.cli("status", "../../auth.json")
        self.assertEqual(code, 1)
        self.assertIn("canonical evaluation UUID", errors)

    def test_legacy_uncertain_yukon_request_keeps_its_operation_key(self):
        client = RemoteClient(self.state)
        body = request_body(self.root / "submission", client.base)
        legacy_request = {**body, "request_id": self.request["request_id"]}
        identity = self.store.create("alice", legacy_request)
        legacy = self.state / "yukon/pending" / (digest({"base": client.base, "body": body}) + ".json")
        private_json(legacy, legacy_request)
        self.assertEqual(self.submit(), identity)
        self.finish_worker()
        code, _, errors = self.cli("wait", identity)
        self.assertEqual(code, 0, errors)
        self.assertFalse(legacy.exists())

    def test_actions_cannot_start_a_run_through_standalone_cli(self):
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            code, _, errors = self.cli("submit", self.root / "submission")
        self.assertEqual(code, 1)
        self.assertIn("retrieve an existing result", errors)
        self.assertIsNone(self.store.claim())
