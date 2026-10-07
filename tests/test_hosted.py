"""Trusted Yukon retrieval: ownership, immutable inputs and no repeat execution."""
import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import uuid

from catalyst.evaluator import JobStore, handler_for
from catalyst.hosted import LEGACY_PROTOCOL, OBJECTIVES, PROTOCOL, ServiceIdentity
from catalyst.problems import initial_problems
from catalyst.remote import digest, request_body, verification_reference
from test_yukon import completed

ROOT = Path(__file__).resolve().parents[1]


class HostedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = JobStore(Path(self.temp.name))
        self.owner = str(uuid.uuid4())
        with patch.dict("os.environ", {"CATALYST_LOCAL_TEST": "", "CATALYST_LOCAL_ECDSA": ""}):
            self.request = {**request_body(ROOT / "harnesses/ecdsa-baseline", "http://127.0.0.1:8778"),
                            "request_id": str(uuid.uuid4())}
        self.id = self.store.create(self.owner, self.request)
        self.store.claim()
        self.store.transition(self.id, "running")
        self.store.transition(self.id, "verifying")
        result = completed(self.request, self.id)
        self.store.transition(self.id, "completed", result)
        self.body = {"protocol": PROTOCOL, "kind": "submission", "owner_id": self.owner,
                     "submission_id": str(uuid.uuid4()), "benchmark_id": str(uuid.uuid4()),
                     "benchmark_revision": "a" * 40, "objectives": OBJECTIVES,
                     "problem": {"id": "ecdsa.fail", "version": digest(self.request["problem_set"])},
                     "reference": verification_reference(result, self.request),
                     "judge": self.request["judge"]}
        self.authorization = {"enabled": True, "problem": copy.deepcopy(self.body["problem"])}
        principals = {"consumer": {"kind": "yukon-service", "id": "yukon",
                                  "benchmarks": {self.body["benchmark_id"]: self.authorization}},
                      "unscoped": {"kind": "yukon-service", "id": "unscoped"},
                      "solver": {"kind": "yukon-solver", "owner": self.owner}}
        auth = ServiceIdentity({"mode": "service", "tokens": {
            hashlib.sha256(key.encode()).hexdigest(): value for key, value in principals.items()}, "grants": {}})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(self.store, auth, initial_problems(), "remote"))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def post(self, body=None, token="consumer", route="/yukon/v1/retrieve"):
        request = Request(f"http://127.0.0.1:{self.server.server_port}{route}",
                          data=json.dumps(body if body is not None else self.body).encode(),
                          headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        try:
            with urlopen(request) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            with error:
                return error.code, json.load(error)

    def test_retries_return_verified_pareto_judgment_without_jobs_or_private_fields(self):
        first = self.post()
        self.assertEqual(first[0], 200, first)
        self.assertEqual(first, self.post())
        self.assertEqual(first[1]["protocol"], "yukon-remote-verification-v1")
        self.assertEqual(first[1]["request"], self.body)
        self.assertEqual(first[1]["artifact"], {
            "kind": "harness-source", "sha256": self.request["source"]["digest"]})
        self.assertNotIn("evaluation_id", first[1])
        public = first[1]["judgment"]
        self.assertEqual(public["scores"], [100, .25])
        for secret in ("grant_local_ecdsa", "archive_base64", "request_id", "owner_id"):
            self.assertNotIn(secret, json.dumps(public))
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM jobs").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM yukon_retrievals").fetchone()[0], 1)
        validity = copy.deepcopy(self.body)
        validity["judge"]["fields"] = {"scores": False, "validity": True}
        status, result = self.post(validity)
        self.assertEqual(status, 200)
        self.assertNotIn("scores", result["judgment"])

    def test_rejects_wrong_identity_reference_policy_and_source_uploads(self):
        self.assertEqual(self.post(token="solver")[0], 403)
        self.assertEqual(self.post(token="unknown")[0], 401)
        for key, value, expected in [
            ("owner_id", str(uuid.uuid4()), 403), ("source_files", {}, 400),
            ("evaluation", {}, 400), ("reference", {}, 409),
            ("judge", {"policies": {}, "fields": {"scores": True, "validity": True}}, 400),
        ]:
            self.assertEqual(self.post({**self.body, key: value})[0], expected, key)
        self.assertEqual(self.post({**self.body, "endpoint": "http://untrusted.invalid"})[0], 400)
        self.assertEqual(self.post({**self.body, "protocol": "catalyst-yukon-v1"})[0], 400)

    def test_receipt_binds_every_retained_identity_without_resubmitting_harness(self):
        for key in ("evaluation_id", "source_digest", "evaluation_config_digest",
                    "problem_set_digest", "policies_digest", "pricing_digest", "image_digest",
                    "evidence_mode"):
            changed = copy.deepcopy(self.body)
            changed["reference"][key] = "forged"
            self.assertEqual(self.post(changed)[0], 409, key)
        forged_score = copy.deepcopy(self.body)
        forged_score["reference"]["scores"] = [1, 0]
        self.assertEqual(self.post(forged_score)[0], 409)
        # The request carries no source archive, hashes or evaluation settings.
        self.assertNotIn("source_files", self.body)
        self.assertNotIn("evaluation", self.body)
        self.assertEqual(self.post()[1]["judgment"]["scores"], [100, .25])

    def test_local_evidence_and_changed_binding_cannot_be_published(self):
        self.assertEqual(self.post()[0], 200)
        changed = {**self.body, "kind": "baseline"}
        self.assertEqual(self.post(changed)[0], 409)
        with self.store.connect() as db:
            local = {**self.request, "evidence_mode": "local-ecdsa"}
            db.execute("UPDATE jobs SET request=? WHERE id=?", (json.dumps(local), self.id))
        self.assertEqual(self.post()[0], 409)

    def test_concurrent_conflicting_bindings_cannot_both_succeed(self):
        bodies = [self.body, {**self.body, "kind": "baseline"}]
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = sorted(result[0] for result in pool.map(self.post, bodies))
        self.assertEqual(statuses, [200, 409])

    def test_pinned_revision_and_objective_order_are_bound(self):
        self.assertEqual(OBJECTIVES, json.loads((ROOT / "benchmark.json").read_text())["objectives"])
        self.assertEqual(self.post()[0], 200)
        self.assertEqual(self.post({**self.body, "benchmark_revision": "b" * 40})[0], 409)
        self.assertEqual(self.post({**self.body, "benchmark_revision": ""})[0], 400)
        self.assertEqual(self.post({**self.body, "objectives": list(reversed(OBJECTIVES))})[0], 409)
        other = [{"name": "accuracy", "direction": "+"}, {"name": "cost", "direction": "-"}]
        self.assertEqual(self.post({**self.body, "objectives": other})[0], 409)
        self.assertEqual(self.post({**self.body, "protocol": "yukon-remote-verification-v2"})[0], 400)
        self.assertEqual(self.post({**self.body, "protocol": LEGACY_PROTOCOL})[0], 400)

    def test_legacy_endpoint_still_serves_deployed_consumers(self):
        body = {key: value for key, value in self.body.items()
                if key not in {"benchmark_revision", "objectives", "problem"}}
        body["protocol"] = LEGACY_PROTOCOL
        status, result = self.post(body, route=f"/evaluations/{self.id}/yukon")
        self.assertEqual(status, 200, result)
        self.assertEqual(result["protocol"], LEGACY_PROTOCOL)
        self.assertEqual(result["reference"], body["reference"])
        self.assertEqual(result["evaluation_id"], self.id)
        self.assertEqual(result["judgment"]["scores"], [100, .25])

    def test_service_key_must_be_enabled_for_this_benchmark(self):
        self.assertEqual(self.post(token="unscoped")[0], 403)
        self.assertEqual(self.post({**self.body, "benchmark_id": str(uuid.uuid4())})[0], 403)
        self.authorization["enabled"] = False
        self.assertEqual(self.post()[0], 403)
        with self.store.connect() as db:
            self.assertIsNone(db.execute(
                "SELECT name FROM sqlite_master WHERE name='yukon_retrievals'").fetchone())

    def test_problem_claim_cannot_authorize_another_problem_or_version(self):
        for key, value in [("id", "another-problem"), ("version", "older-dataset")]:
            wrong = {**self.body["problem"], key: value}
            self.assertEqual(self.post({**self.body, "problem": wrong})[0], 409)
            # Even when BOTH operator configs agree on the wrong problem, the
            # actual stored evaluation must match before any judgment is released.
            self.authorization["problem"] = wrong
            self.assertEqual(self.post({**self.body, "problem": wrong})[0], 409)
            self.authorization["problem"] = copy.deepcopy(self.body["problem"])
        forged = copy.deepcopy(self.body)
        forged["reference"]["problem_set_digest"] = "forged"
        self.assertEqual(self.post(forged)[0], 409)
        self.assertEqual(self.post()[0], 200)
