"""Contract tests with a synthetic HTTP evaluator; no builds or model calls."""
import base64
from contextlib import redirect_stderr, redirect_stdout
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid

from catalyst.common import CatalystError, open_bundle, read_json, write_json
from catalyst.yukon import authentication
from catalyst.receipts import check_receipt, PROTOCOL as RECEIPT_PROTOCOL
from harness_fixture import create_harness
from catalyst.remote import (
    PROTOCOL, bound_result, digest, endpoint, evaluation_config,
    judge_input, judgment, request_lock, SCORING, VALIDITY, RemoteClient, verification_reference,
)

from catalyst.tiers import pricing_digest

PROJECT = Path(__file__).resolve().parents[1]


def completed(request, evaluation_id):
    return {
        "protocol": PROTOCOL, "evaluation_id": evaluation_id, "status": "completed",
        "request_id": request["request_id"], "source_digest": request["source"]["digest"],
        "evaluation_config_digest": digest(request["evaluation"]),
        "problem_set_digest": digest(request["problem_set"]),
        "policies_digest": digest(request["judge"]["policies"]),
        "pricing_digest": digest(request["pricing"]),
        "evidence_mode": request.get("evidence_mode", "remote"),
        "build": {"id": "fixture-build", "image_digest": "sha256:" + "a" * 64},
        "valid": True, "reason": "Synthetic contract-test observations only.",
        "trace_available": True, "private_debug": "must not enter public judgment",
        "observations": [
            {"problem_id": p["id"], "problem_commit": p["repository"]["commit"],
             "normalized_model_usd": 0.25, "pricing_digest": pricing_digest(), "end_sequence": 4,
             "usage": [{"sequence": 1, "request_id": "call-1", "settled": True,
                        "tokens": {"input_tokens": 20000, "output_tokens": 5000,
                                   "cached_read_tokens": 0, "cache_write_tokens": 0}}],
             "checkpoints": [{"budget_tier": request["evaluation"]["max_model_credits"],
                              "sequence": 3, "settled": True}],
             "curve": [{"performance": 100, "avg_toffoli": 10, "peak_qubits": 10,
                        "normalized_model_usd": 0.25, "captured_sequence": 2,
                        "candidate_digest": "c" * 64, "verified_candidate_digest": "c" * 64,
                        "settled": True, "verified": True}],
             "private_tool_output": "must not enter public judgment"}
            for p in request["problem_set"]
        ],
    }


class YukonRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        create_harness(self.root / "submission")
        self.state = self.root / ".catalyst"
        self.target = self.state / "yukon/score.json"
        self.config = read_json(self.root / "submission/evaluation.json")
        self.config["llm_access"]["grant_id"] = "grant_contract_test"
        write_json(self.root / "submission/evaluation.json", self.config)
        self.input = {"policies": {"scoring": SCORING, "validity": VALIDITY},
                      "fields": {"scores": True, "validity": True}}
        self.requests, self.jobs, self.polls, self.trace_gets, self.publications = [], {}, [], [], []
        self.fail_post_once = False
        self.transform = lambda result: result
        test = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def respond(self, status, value):
                data = value if isinstance(value, bytes) else json.dumps(value).encode()
                self.send_response(status)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def authorized(self):
                if self.headers.get("Authorization") != "Bearer test-yukon-token":
                    self.respond(401, {"error": "unauthorized"})
                    return False
                return True

            def do_POST(self):
                if not self.authorized():
                    return
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path == "/verifications/retrieve":
                    test.publications.append(request)
                    reference = request["reference"]
                    original, identity = next(job for job in test.jobs.values()
                                              if job[1] == reference["evaluation_id"])
                    result = test.transform(completed(original, identity))
                    if reference != verification_reference(result, original):
                        return self.respond(403, {"error": "Receipt does not match retained evidence."})
                    return self.respond(200, {
                        **request, "protocol": RECEIPT_PROTOCOL,
                        "artifact": {"kind": "harness-source", "sha256": reference["source_digest"]},
                        "judgment": judgment(result, original),
                    })
                test.requests.append(request)
                snapshot, files = open_bundle(base64.b64decode(request["source"]["archive_base64"]))
                test.assertEqual(snapshot["version"], request["source"]["digest"])
                test.assertNotIn("evaluation.json", files)
                test.assertNotIn("test-yukon-token", json.dumps(request))
                key = request["request_id"]
                if key not in test.jobs:
                    test.jobs[key] = (request, str(uuid.uuid4()))
                if test.fail_post_once:
                    test.fail_post_once = False
                    self.respond(503, {"error": "fixture lost acknowledgement"})
                    return
                self.respond(202, {"request_id": key, "evaluation_id": test.jobs[key][1]})

            def do_GET(self):
                if not self.authorized():
                    return
                identity = self.path.split("/")[2]
                request, _ = next(job for job in test.jobs.values() if job[1] == identity)
                if self.path.endswith("/traces"):
                    test.trace_gets.append(identity)
                    self.respond(200, b"private fixture traces")
                    return
                test.polls.append(identity)
                result = completed(request, identity)
                if test.polls.count(identity) == 1:
                    result["status"] = "queued"
                self.respond(200, test.transform(result))

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.environ = patch.dict(os.environ, {
            "YUKON_API_TOKEN": "test-yukon-token", "GITHUB_ACTIONS": "",
            "CATALYST_API_TOKEN": "", "CATALYST_LOCAL_TEST": "", "CATALYST_LOCAL_ECDSA": "",
            "YUKON_EVALUATION": json.dumps(self.input), "CATALYST_EVALUATOR_URL": self.base,
        })
        self.environ.start()

    def tearDown(self):
        self.environ.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def evaluate(self):
        self.target.unlink(missing_ok=True)
        with patch("catalyst.remote.time.sleep"), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            client = RemoteClient(self.state)
            identity = client.submit(self.root / "submission")["evaluation_id"]
            artifact = client.wait(identity)
            client.export_reference(identity)
            write_json(self.target, artifact)
            return artifact

    def retrieve(self):
        with redirect_stdout(io.StringIO()):
            return check_receipt(self.root)

    def test_remote_ecdsa_tier_judgment_and_private_trace_download(self):
        artifact = self.evaluate()
        self.assertEqual(artifact["scores"], [100, 0.25])
        self.assertTrue(artifact["valid"])
        self.assertEqual(read_json(self.target), artifact)
        self.assertEqual(len(self.trace_gets), 1)
        folder = self.state / "remote/evaluations" / self.trace_gets[0]
        self.assertEqual((folder / "traces.zip").read_bytes(), b"private fixture traces")
        self.assertEqual((folder / "traces.zip").stat().st_mode & 0o777, 0o600)
        public = json.dumps(artifact)
        for private in ("grant_contract_test", "test-yukon-token", "private_tool_output", "private_debug"):
            self.assertNotIn(private, public)
        self.assertEqual(len(list((self.state / "remote/pending").glob("*.json"))), 0)

    def test_repeated_evaluations_and_changed_budget_reuse_source_identity(self):
        self.evaluate()
        self.evaluate()
        self.config["max_model_credits"] = 200
        write_json(self.root / "submission/evaluation.json", self.config)
        self.evaluate()
        self.assertEqual(len(self.jobs), 3)
        self.assertEqual(len({r["source"]["digest"] for r in self.requests}), 1)
        self.assertNotEqual(digest(self.requests[0]["evaluation"]), digest(self.requests[-1]["evaluation"]))

    def test_workflow_reads_root_receipt_without_source_or_another_evaluation(self):
        original = self.evaluate()
        write_json(self.root / "verification.json", read_json(self.root / "submission/verification.json"))
        shutil.rmtree(self.root / "submission")
        published = self.retrieve()
        self.assertEqual(published["scores"], original["scores"])
        self.assertTrue(published["valid"])
        self.assertEqual(len(self.jobs), 1)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(len(self.publications), 1)
        self.assertEqual(len(self.trace_gets), 1)
        self.assertFalse((self.root / "submission").exists())

    def test_cheaper_result_qualifies_for_all_views_without_missing_yukon_values(self):
        self.config["max_model_credits"] = 200
        write_json(self.root / "submission/evaluation.json", self.config)
        artifact = self.evaluate()
        self.assertEqual(artifact["scores"], [100, 0.25])
        summaries = artifact["metrics"]["observations"][0]["tiers"]
        self.assertEqual([t["budget_tier"] for t in summaries], [10, 20, 50, 100])
        self.assertEqual([t["status"] for t in summaries], ["eligible"] * 4)
        self.assertEqual(summaries[0]["best"]["performance"], 100)

    def test_no_verified_candidate_cannot_publish_a_valid_score(self):
        def late(result):
            result["observations"][0]["curve"] = []
            return result
        self.transform = late
        with self.assertRaisesRegex(CatalystError, "no verified candidate"):
            self.evaluate()
        self.assertFalse(self.target.exists())

    def test_pricing_binding_mismatch_cannot_publish_or_download_traces(self):
        self.transform = lambda result: {**result, "pricing_digest": "f" * 64}
        with self.assertRaisesRegex(CatalystError, "does not match"):
            self.evaluate()
        self.assertFalse(self.target.exists())
        self.assertEqual(self.trace_gets, [])

    def test_forged_receipt_cannot_publish_scores(self):
        self.evaluate()
        reference = read_json(self.root / "submission/verification.json")
        # Even a valid baseline cannot hide a forged submitted receipt.
        write_json(self.root / "verification.json", reference)
        write_json(self.root / "submission/verification.json",
                   {**reference, "image_digest": "sha256:" + "f" * 64})
        with self.assertRaises(CatalystError):
            self.retrieve()
        self.assertFalse(self.target.exists())
        self.assertEqual(len(self.jobs), 1)

    def test_registered_receipt_path_takes_precedence_over_root_baseline(self):
        original = self.evaluate()
        write_json(self.root / "verification.json", {"evaluation_id": "wrong-baseline"})
        published = self.retrieve()
        self.assertEqual(published["scores"], original["scores"])
        self.assertEqual(len(self.jobs), 1)

    def test_dangling_uploaded_receipt_cannot_fall_back_to_baseline(self):
        self.evaluate()
        receipt = self.root / "submission/verification.json"
        write_json(self.root / "verification.json", read_json(receipt))
        receipt.unlink()
        receipt.symlink_to(self.root / "absent.json")
        with self.assertRaisesRegex(CatalystError, "symlinks"):
            self.retrieve()

    def test_missing_root_receipt_removes_stale_score_without_starting_a_run(self):
        write_json(self.target, {"scores": [999]})
        with self.assertRaisesRegex(CatalystError, "Missing verification.json"):
            self.retrieve()
        self.assertFalse(self.target.exists())
        self.assertEqual(self.requests, [])

    def test_lost_acknowledgement_reuses_operation_without_duplicate_job(self):
        write_json(self.target, {"scores": [999]})
        self.fail_post_once = True
        with self.assertRaisesRegex(CatalystError, "HTTP 503"):
            self.evaluate()
        self.assertFalse(self.target.exists())
        self.assertEqual(len(list((self.state / "remote/pending").glob("*.json"))), 1)
        self.evaluate()
        self.assertEqual(len(self.jobs), 1)
        self.assertEqual(self.requests[0]["request_id"], self.requests[1]["request_id"])

    def test_wrong_source_result_never_becomes_yukon_score(self):
        self.transform = lambda result: {**result, "source_digest": "f" * 64}
        write_json(self.target, {"scores": [999]})
        with self.assertRaisesRegex(CatalystError, "does not match"):
            self.evaluate()
        self.assertFalse(self.target.exists())
        self.assertEqual(self.trace_gets, [])

    def test_invalid_proof_retains_traces_and_explicit_invalidity(self):
        self.transform = lambda result: {**result, "valid": False, "observations": [],
                                         "reason": "ECDSA circuit verification failed."}
        artifact = self.evaluate()
        self.assertFalse(artifact["valid"])
        self.assertIsNone(artifact["scores"])
        self.assertEqual(len(self.trace_gets), 1)

    def test_worker_failure_has_no_judgment_but_keeps_traces(self):
        self.transform = lambda result: {**result, "status": "failed"}
        with self.assertRaisesRegex(CatalystError, "failed"):
            self.evaluate()
        self.assertFalse(self.target.exists())
        self.assertEqual(len(self.trace_gets), 1)

    def test_configuration_missing_grant_or_secret_field_fails_before_network(self):
        for changes in ({"grant_id": ""}, {"grant_id": "grant_contract_test", "api_key": "secret"}):
            write_json(self.root / "submission/evaluation.json", {**self.config, "llm_access": changes})
            with self.assertRaisesRegex(CatalystError, "grant reference"):
                self.evaluate()
        self.assertEqual(self.requests, [])

    def test_policy_scope_and_bound_observations_fail_closed(self):
        self.evaluate()
        request, identity = next(iter(self.jobs.values()))
        result = completed(request, identity)
        bound_result(result, request, identity)
        for mutation in (
            lambda r: r["observations"].pop(),
            lambda r: r["observations"][0].update(problem_commit="b" * 40),
            lambda r: r["observations"][0].update(normalized_model_usd=100),
            lambda r: r["observations"][0]["curve"][0].update(performance=float("nan")),
            lambda r: r["observations"][0]["curve"][0].update(performance=999),
            lambda r: r.update(trace_available=False),
            lambda r: r.update(build={"id": "client-build", "image_digest": "mutable:tag"}),
        ):
            malformed = copy.deepcopy(result)
            mutation(malformed)
            with self.assertRaises(CatalystError):
                judgment(malformed, request)
        for bad in (
            {**self.input, "policies": {"scoring": {"version": "unknown"}, "validity": VALIDITY}},
            {**self.input, "fields": {"scores": 1, "validity": True}},
            {**self.input, "fields": {"scores": False, "validity": False}},
        ):
            with self.assertRaises(CatalystError):
                judge_input(json.dumps(bad))
        request["judge"]["fields"] = {"scores": False, "validity": True}
        self.assertNotIn("scores", judgment(result, request))
        request["judge"]["fields"] = {"scores": True, "validity": False}
        self.assertNotIn("valid", judgment(result, request))

    def test_concurrent_client_cannot_issue_same_paid_request(self):
        pending = self.state / "pending/request.json"
        with request_lock(pending):
            with self.assertRaisesRegex(CatalystError, "already running"):
                with request_lock(pending):
                    self.fail("Concurrent paid request was allowed.")

    def test_redirect_refused_and_non_https_remote_endpoint_rejected(self):
        # This exercises the actual authorization transport's redirect handler.
        from catalyst.remote import NoRedirect
        with self.assertRaisesRegex(CatalystError, "redirects"):
            NoRedirect().redirect_request(None, None, 302, "", {}, "https://elsewhere.test")
        for url in ("http://remote.test", "https://token@remote.test", "https://remote.test?token=secret"):
            with patch.dict(os.environ, {"CATALYST_EVALUATOR_URL": url}):
                with self.assertRaises(CatalystError):
                    endpoint()

    def test_yukon_config_login_and_workflow_oidc(self):
        config_dir = self.root / "config"
        write_json(config_dir / "yukon/config.json", {"token": "private-config-token"})
        with patch.dict(os.environ, {"YUKON_CONFIG_DIR": str(config_dir), "YUKON_API_TOKEN": "",
                                    "HILBERT_API_TOKEN": "", "SUPABASE_ACCESS_TOKEN": ""}):
            token, context = authentication()
            self.assertEqual(token, "private-config-token")
            self.assertEqual(context, {"kind": "yukon-solver"})
        with patch.dict(os.environ, {
            "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": "org/catalyst",
            "GITHUB_SHA": "c" * 40, "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1",
            "ACTIONS_ID_TOKEN_REQUEST_URL": "https://actions.test/oidc?job=1",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "github-job-token",
        }), patch("catalyst.yukon.fetch", return_value=b'{"value":"signed-oidc"}') as oidc:
            token, context = authentication()
            self.assertEqual(token, "signed-oidc")
            self.assertEqual(context["commit"], "c" * 40)
            self.assertIn("audience=catalyst-evaluator", oidc.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
