"""Trusted Yukon retrieval: ownership, immutable inputs and no repeat execution."""
import base64
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

from catalyst.common import open_bundle
from catalyst.evaluator import JobStore, handler_for
from catalyst.hosted import PROTOCOL, ServiceIdentity
from catalyst.problems import initial_problems
from catalyst.remote import request_body, verification_reference
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
        snapshot, _ = open_bundle(base64.b64decode(self.request["source"]["archive_base64"]))
        self.body = {"protocol": PROTOCOL, "kind": "submission", "owner_id": self.owner,
                     "submission_id": str(uuid.uuid4()), "benchmark_id": str(uuid.uuid4()),
                     "reference": verification_reference(result, self.request),
                     "source_files": snapshot["files"], "evaluation": self.request["evaluation"],
                     "judge": self.request["judge"]}
        principals = {"consumer": {"kind": "yukon-service", "id": "yukon"},
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

    def post(self, body=None, token="consumer", suffix="yukon"):
        request = Request(f"http://127.0.0.1:{self.server.server_port}/evaluations/{self.id}/{suffix}",
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

    def test_rejects_wrong_identity_source_configuration_reference_and_policy(self):
        self.assertEqual(self.post(token="solver")[0], 403)
        self.assertEqual(self.post(token="unknown")[0], 401)
        for key, value, expected in [
            ("owner_id", str(uuid.uuid4()), 403), ("source_files", {}, 409),
            ("evaluation", {}, 409), ("reference", {}, 409),
            ("judge", {"policies": {}, "fields": {"scores": True, "validity": True}}, 400),
        ]:
            self.assertEqual(self.post({**self.body, key: value})[0], expected, key)
        self.assertEqual(self.post({**self.body, "endpoint": "http://untrusted.invalid"})[0], 400)

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
