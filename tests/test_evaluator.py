"""Real API/store/worker contracts; backend execution is separately exercised by check-local-e2e."""
import base64
import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import uuid

from catalyst.common import CatalystError, read_json, snapshot_directory, write_json
from catalyst.evaluator import APIError, JobStore, LocalIdentity, handler_for
from catalyst.executable import SOURCE_EXCLUDES
from catalyst.local_run import WORKFLOW_CONTEXT
from catalyst.problems import initial_problems
from catalyst.tiers import pricing_schedule
from catalyst.worker import collect_usage, run_one, worker_lock
from catalyst.remote import PROTOCOL, judge_input, judgment
from test_yukon import completed

PROJECT = Path(__file__).resolve().parents[1]


class EvaluatorFixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        submission = self.root / "submission"
        shutil.copytree(PROJECT / "submission", submission)
        # Tests start with unevaluated harnesses, not the real starter receipt.
        (submission / "verification.json").unlink(missing_ok=True)
        evaluation = read_json(submission / "evaluation.json")
        evaluation["llm_access"]["grant_id"] = "grant_contract_test"
        write_json(submission / "evaluation.json", evaluation)
        snapshot, archive = snapshot_directory(submission, exclude=SOURCE_EXCLUDES)
        self.request = {
            "request_id": str(uuid.uuid4()), "protocol": PROTOCOL,
            "source": {"digest": snapshot["version"], "archive_base64": base64.b64encode(archive).decode()},
            "evaluation": evaluation, "problem_set": initial_problems(), "pricing": pricing_schedule(),
            "judge": judge_input(None), "context": {"kind": "yukon-solver"}, "evidence_mode": "local-test",
        }
        self.store = JobStore(self.root / "service")
        principals = {"alice-token": {"kind": "yukon-solver", "owner": "alice"},
                      "bob-token": {"kind": "yukon-solver", "owner": "bob"},
                      "workflow-token": {"kind": "github-actions", "context": WORKFLOW_CONTEXT}}
        self.auth = LocalIdentity({
            "mode": "local-test",
            "tokens": {hashlib.sha256(key.encode()).hexdigest(): value for key, value in principals.items()},
            "grants": {"grant_contract_test": {"owner": "alice", "model": evaluation["model"],
                                              "max_model_credits": 200, "limits": evaluation["limits"]}},
        })
        self.server = ThreadingHTTPServer(("127.0.0.1", 0),
                                         handler_for(self.store, self.auth, initial_problems()))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def http(self, path, token="alice-token", body=None):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.server.server_port}{path}",
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request) as response:
                data = response.read()
                return response.status, data if path.endswith("/traces") else json.loads(data)
        except urllib.error.HTTPError as error:
            with error:
                return error.code, json.loads(error.read())

    def create(self):
        status, result = self.http("/evaluations", body=self.request)
        self.assertEqual(status, 202, result)
        return result["evaluation_id"]

    def complete(self):
        test = self

        class Backend:
            def evaluate(self, job, artifacts, transition):
                transition("running")
                transition("verifying")
                # Fast contract data only; Docker execution has its own integration test.
                return completed(test.request, job["id"])

        evaluation_id = self.create()
        self.assertEqual(run_one(self.store, Backend()), evaluation_id)
        self.assertEqual(self.store.get(evaluation_id)["status"], "completed")
        return evaluation_id


class EvaluatorTests(EvaluatorFixture, unittest.TestCase):
    def test_authenticated_submission_and_owner_only_results_and_traces(self):
        self.assertEqual(self.http("/evaluations", "unknown", self.request)[0], 401)
        self.assertEqual(self.http("/evaluations", "bob-token", self.request)[0], 403)
        self.assertEqual(self.http("/evaluations", "workflow-token", self.request)[0], 403)
        evaluation_id = self.complete()
        for suffix in ("", "/traces"):
            path = f"/evaluations/{evaluation_id}{suffix}"
            self.assertEqual(self.http(path, "bob-token")[0], 404)
            self.assertEqual(self.http(path, "workflow-token")[0], 404)
            self.assertEqual(self.http(path)[0], 200)

    def test_idempotent_post_and_conflicting_payload(self):
        evaluation_id = self.create()
        self.assertEqual(self.create(), evaluation_id)
        changed = copy.deepcopy(self.request)
        changed["evaluation"]["max_model_credits"] = 200
        self.assertEqual(self.http("/evaluations", body=changed)[0], 409)
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM jobs").fetchone()[0], 1)

    def test_rejects_untrusted_pins_limits_and_source(self):
        for key, value in (("evidence_mode", "remote"), ("pricing", {}), ("problem_set", [])):
            request = {**self.request, key: value}
            self.assertEqual(self.http("/evaluations", body=request)[0], 400)
        changed = copy.deepcopy(self.request)
        changed["evaluation"]["max_model_credits"] = 201
        self.assertEqual(self.http("/evaluations", body=changed)[0], 403)
        changed = copy.deepcopy(self.request)
        changed["source"]["digest"] = "a" * 64
        self.assertEqual(self.http("/evaluations", body=changed)[0], 400)

    def test_claim_is_atomic_and_completed_job_is_not_restarted(self):
        evaluation_id = self.create()
        with ThreadPoolExecutor(max_workers=4) as executor:
            claims = list(executor.map(lambda _: self.store.claim(), range(4)))
        self.assertEqual([job["id"] for job in claims if job], [evaluation_id])
        self.assertIsNone(self.store.claim())

    def test_recovery_preserves_queue_and_never_replays_started_work(self):
        first = self.create()
        self.store.claim()
        queued = self.store.create("alice", {**self.request, "request_id": str(uuid.uuid4())})
        restarted = JobStore(self.root / "service")
        with worker_lock(restarted):
            restarted.recover_interrupted()
        self.assertEqual(restarted.get(first)["status"], "failed")
        self.assertEqual(restarted.get(queued)["status"], "queued")
        self.assertEqual(restarted.create("alice", self.request), first)
        self.assertEqual(restarted.claim()["id"], queued)

    def test_single_worker_lock(self):
        with worker_lock(self.store):
            with self.assertRaisesRegex(CatalystError, "already owns"):
                with worker_lock(JobStore(self.root / "service")):
                    pass

    def test_failure_retains_private_details_and_does_not_requeue(self):
        class Broken:
            def evaluate(self, *args):
                raise RuntimeError("private failure detail")

        evaluation_id = self.create()
        run_one(self.store, Broken())
        response = self.http(f"/evaluations/{evaluation_id}")[1]
        self.assertEqual(response["status"], "failed")
        self.assertNotIn("private failure detail", json.dumps(response))
        self.assertEqual(self.create(), evaluation_id)
        self.assertIsNone(self.store.claim())
        self.assertIn(b"PK", self.http(f"/evaluations/{evaluation_id}/traces")[1][:2])

    def test_workflow_requires_registered_owner_and_exact_source_then_reuses_result(self):
        evaluation_id = self.complete()
        body = {k: v for k, v in self.request.items() if k != "request_id"}
        body["context"] = WORKFLOW_CONTEXT
        path = f"/evaluations/{evaluation_id}/submissions"
        self.assertEqual(self.http(path, "workflow-token", body)[0], 403)
        with self.assertRaises(APIError):
            self.store.register_submission(evaluation_id, "bob", "local/catalyst", "c" * 40)
        self.store.register_submission(evaluation_id, "alice", "local/catalyst", "c" * 40)
        changed = copy.deepcopy(body)
        changed["evaluation"]["max_model_credits"] = 200
        self.assertEqual(self.http(path, "workflow-token", changed)[0], 409)
        changed = copy.deepcopy(body)
        changed["context"] = {**WORKFLOW_CONTEXT, "commit": "d" * 40}
        self.assertEqual(self.http(path, "workflow-token", changed)[0], 403)
        for _ in range(2):
            status, result = self.http(path, "workflow-token", body)
            self.assertEqual(status, 200)
            self.assertEqual(result, self.store.view(evaluation_id))
        self.assertIsNone(self.store.claim())
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM publications").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM jobs").fetchone()[0], 1)

    def test_local_evidence_cannot_be_projected_as_official(self):
        result = completed(self.request, str(uuid.uuid4()))
        with self.assertRaisesRegex(CatalystError, "Local-test"):
            judgment(result, {**self.request, "evidence_mode": "remote"})

    def test_gateway_usage_must_reconcile_with_terminal_record(self):
        usage = self.root / "usage"
        usage.mkdir()
        event = {"source": "gateway", "kind": "model.accounting", "request_id": "call-1",
                 "data": {"accounting_method": "gateway", "provider": "openai", "model": "gpt-5.6-sol",
                          "input_tokens": 20000, "output_tokens": 5000}}
        (usage / "events.jsonl").write_text(json.dumps(event) + "\n")
        write_json(self.root / "record.json", {"data": {"usage": {"normalized_usd": .25}}})
        ledger, total = collect_usage(self.root, self.request["evaluation"])
        self.assertEqual(len(ledger), 1)
        self.assertEqual(float(total), .25)
        write_json(self.root / "record.json", {"data": {"usage": {"normalized_usd": .20}}})
        with self.assertRaisesRegex(CatalystError, "disagrees"):
            collect_usage(self.root, self.request["evaluation"])
        write_json(self.root / "record.json", {"data": {"usage": {"normalized_usd": .25}}})
        (usage / "events.jsonl").write_text((json.dumps(event) + "\n") * 2)
        with self.assertRaisesRegex(CatalystError, "Duplicate"):
            collect_usage(self.root, self.request["evaluation"])
