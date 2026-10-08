"""Yukon login/session contract over the real local HTTP API; no paid runs."""
import copy
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import uuid

import jwt

from catalyst.common import CatalystError, read_json, write_json
from catalyst.evaluator import APIError, JobStore, handler_for
from catalyst.hosted import ServiceIdentity
from catalyst.problems import initial_problems
from catalyst.receipts import PROTOCOL as RECEIPT_PROTOCOL, check_receipt, problem_identity
from catalyst.remote import (
    HTTPFailure, RemoteClient, _solver_sessions, fetch, request_body, solver_fetch,
    solver_token, verification_reference,
)
from catalyst.yukon_auth import PROTOCOL, SESSION_SECONDS, YukonLogin, configure_yukon_login
from test_yukon import completed

ROOT = Path(__file__).resolve().parents[1]
KEY = "ykn_test_secret_never_persist"
OTHER_KEY = "ykn_other_secret_never_persist"


class YukonAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.owner, self.other = str(uuid.uuid4()), str(uuid.uuid4())
        self.store = JobStore(self.root / "service")
        self.env = patch.dict(os.environ, {"CATALYST_LOCAL_TEST": "", "CATALYST_LOCAL_ECDSA": "",
                                          "GITHUB_ACTIONS": "", "YUKON_API_TOKEN": KEY})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.request = {**request_body(ROOT / "harnesses/ecdsa-baseline", "http://127.0.0.1:8778"),
                        "request_id": str(uuid.uuid4())}
        self.config = {
            "mode": "service", "tokens": {}, "grants": {},
            "yukon_login": {"api_url": "https://api-dev.yukon.org"},
            "solver_policy": {"evaluation": copy.deepcopy(self.request["evaluation"]),
                              "max_active_per_owner": 1, "max_active_total": 2, "max_daily_per_owner": 3},
        }
        self.auth = ServiceIdentity(self.config)
        self.upstream = patch("catalyst.yukon_auth.fetch", side_effect=self.account).start()
        self.addCleanup(patch.stopall)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0),
            handler_for(self.store, self.auth, initial_problems(), "remote"))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        os.environ["CATALYST_EVALUATOR_URL"] = self.base
        _solver_sessions.clear()
        self.addCleanup(_solver_sessions.clear)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def account(self, url, token, **kwargs):
        self.assertEqual(url, "https://api-dev.yukon.org/api/me")
        self.assertEqual(kwargs, {"limit": 65536, "timeout": 10})
        if token not in (KEY, OTHER_KEY):
            raise HTTPFailure(401)
        return json.dumps({"account": {"id": self.owner if token == KEY else self.other},
                           "apiKey": {"private": "must-not-retain"}}).encode()

    def exchange(self, key=KEY):
        return json.loads(fetch(self.base + "/auth/yukon", key, document={"protocol": PROTOCOL}))

    def call(self, route, body=None, key=KEY):
        return json.loads(solver_fetch(self.base, route, key, document=body))

    def assert_http(self, status, operation):
        with self.assertRaises(HTTPFailure) as raised:
            operation()
        self.assertEqual(raised.exception.status, status)

    def completed_receipt(self):
        evaluation = self.store.create(self.owner, self.request)
        self.store.claim()
        self.store.transition(evaluation, "running")
        self.store.transition(evaluation, "verifying")
        result = completed(self.request, evaluation)
        self.store.transition(evaluation, "completed", result)
        return evaluation, verification_reference(result, self.request)

    def test_new_yukon_user_can_submit_without_provisioned_password_or_grant(self):
        client = RemoteClient(self.root / "client")
        first = client.submit(ROOT / "harnesses/ecdsa-baseline")
        self.assertEqual(client.status(first["evaluation_id"])["status"], "queued")
        self.assertEqual(client.submit(ROOT / "harnesses/ecdsa-baseline"), first)
        self.assertEqual(self.upstream.call_count, 1)
        job = self.store.get(first["evaluation_id"])
        self.assertEqual(job["owner"], self.owner)
        self.assertEqual(self.config["tokens"], {})
        self.assertEqual(self.config["grants"], {})
        for path in self.root.rglob("*"):
            if path.is_file():
                data = path.read_bytes()
                self.assertNotIn(KEY.encode(), data, str(path))
                self.assertNotIn(b"cys_", data, str(path))
                self.assertNotIn(b"must-not-retain", data, str(path))

    def test_private_results_and_receipts_are_owner_bound(self):
        evaluation, reference = self.completed_receipt()
        body = {"protocol": RECEIPT_PROTOCOL, "reference": reference,
                "problem": problem_identity(), "judge": self.request["judge"]}
        self.assertEqual(self.call("/verifications/retrieve", body)["judgment"]["scores"], [100, .25])
        self.assert_http(403, lambda: self.call("/verifications/retrieve", body, OTHER_KEY))
        self.assert_http(404, lambda: self.call(f"/evaluations/{evaluation}", key=OTHER_KEY))
        self.assert_http(404, lambda: self.call(f"/evaluations/{evaluation}/traces", key=OTHER_KEY))
        self.assert_http(403, lambda: self.call("/yukon/v1/retrieve", {}))
        write_json(self.root / "submission/verification.json", reference)
        self.assertEqual(check_receipt(self.root)["scores"], [100, .25])
        self.assertEqual(self.upstream.call_count, 2)

    def test_session_renews_after_server_restart_and_expiry(self):
        first = self.call("/evaluations", self.request)
        self.auth.yukon = YukonLogin(self.config["yukon_login"])
        self.assertEqual(self.call("/evaluations", self.request), first)
        self.assertEqual(self.upstream.call_count, 2)
        with patch("catalyst.remote.time.monotonic", return_value=time.monotonic() + SESSION_SECONDS):
            self.assertEqual(self.call("/evaluations", self.request), first)
        self.assertEqual(self.upstream.call_count, 3)
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM jobs").fetchone()[0], 1)

    def test_session_cannot_change_owner_scope_issuer_signature_or_lifetime(self):
        session = self.exchange()
        token = session["access_token"]
        claims = jwt.decode(token[4:], options={"verify_signature": False})
        self.assertEqual(self.auth.authenticate("Bearer " + token)["owner"], self.owner)
        for changed in ({"exp": int(time.time()) - 1}, {"scope": "service"},
                        {"iss": "https://evil.invalid"}, {"aud": "github-actions"}, {"sub": "bad"}):
            forged = "cys_" + jwt.encode({**claims, **changed}, self.auth.yukon.signing_key, algorithm="HS256")
            self.assert_http(401, lambda: fetch(self.base + "/evaluations/" + str(uuid.uuid4()), forged))
        forged = "cys_" + jwt.encode({**claims, "sub": self.other}, b"x" * 32, algorithm="HS256")
        self.assert_http(401, lambda: fetch(self.base + "/evaluations/" + str(uuid.uuid4()), forged))
        self.assertNotIn(KEY, json.dumps(session))
        self.assertNotIn("must-not-retain", repr(vars(self.auth.yukon)))

    def test_rejects_invalid_keys_upstream_errors_and_client_selected_issuer(self):
        self.assert_http(401, lambda: self.exchange("ykn_forged"))
        self.assert_http(401, lambda: self.exchange("invented-locally"))
        self.assert_http(400, lambda: fetch(self.base + "/auth/yukon", KEY,
            document={"protocol": PROTOCOL, "api_url": "https://evil.invalid"}))
        calls = self.upstream.call_count
        self.assert_http(413, lambda: fetch(self.base + "/auth/yukon", KEY, document={"x": "x" * 1024}))
        self.assertEqual(self.upstream.call_count, calls)
        for value in (HTTPFailure(429), HTTPFailure(500), CatalystError("redirect"),
                      b'{"account":{"id":"bad"}}', b'{}', b'null', b'not-json'):
            with self.subTest(value=type(value)):
                self.upstream.side_effect = value if isinstance(value, Exception) else None
                self.upstream.return_value = value
                self.assert_http(503, self.exchange)
        self.assert_http(401, lambda: fetch(self.base + "/evaluations/" + str(uuid.uuid4()), KEY))

    def test_resource_policy_and_atomic_quotas_apply_to_every_yukon_user(self):
        for field, value in (("limits", {"max_seconds": 61, "max_model_tokens": 100000}),
                             ("llm_access", {"grant_id": "grant_other_private"})):
            request = copy.deepcopy(self.request)
            request["evaluation"][field] = value
            self.assert_http(403, lambda: self.call("/evaluations", request))
        session = self.exchange()["access_token"]
        requests = [{**self.request, "request_id": str(uuid.uuid4())} for _ in range(2)]
        def submit(request):
            try:
                return json.loads(fetch(self.base + "/evaluations", session, document=request))["evaluation_id"]
            except HTTPFailure as error:
                return error.status
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, requests))
        self.assertEqual(results.count(429), 1)
        # A different authenticated user gets their own active-run allowance.
        self.call("/evaluations", self.request, OTHER_KEY)
        self.config["solver_policy"]["max_active_per_owner"] = 3
        self.assert_http(429, lambda: self.call("/evaluations", {**self.request, "request_id": str(uuid.uuid4())}))
        with self.store.connect() as db:
            db.execute("UPDATE jobs SET status='failed'")
        self.config["solver_policy"]["max_daily_per_owner"] = 1
        self.assert_http(429, lambda: self.call("/evaluations", {**self.request, "request_id": str(uuid.uuid4())}))

    def test_comparison_checkpoints_do_not_cap_the_solver_requested_budget(self):
        request = copy.deepcopy(self.request)
        request["evaluation"]["max_model_credits"] = 20000
        accepted = self.call("/evaluations", request)
        stored = self.store.get(accepted["evaluation_id"])
        self.assertEqual(stored["request"]["evaluation"]["max_model_credits"], 20000)
        self.assertEqual(stored["owner"], self.owner)

    def test_configure_preserves_oidc_and_consumers_disables_legacy_solver_keys(self):
        auth_path, worker_path = self.root / "auth.json", self.root / "worker.json"
        config = {"mode": "service", "tokens": {"old": {"kind": "yukon-solver", "owner": self.owner},
                    "consumer": {"kind": "yukon-service"}}, "grants": {"existing": {}},
                  "github": {"repositories": {}}}
        write_json(auth_path, config)
        write_json(worker_path, {"mode": "remote", "model_access": "disabled"})
        result = configure_yukon_login(auth_path, "https://api-dev.yukon.org/", worker_path)
        saved = read_json(auth_path)
        self.assertEqual(saved["tokens"], {"consumer": {"kind": "yukon-service"}})
        self.assertEqual(saved["github"], config["github"])
        self.assertEqual(saved["grants"], config["grants"])
        self.assertEqual(saved["yukon_login"]["api_url"], "https://api-dev.yukon.org")
        self.assertEqual(result["session_seconds"], 900)
        self.assertEqual(auth_path.stat().st_mode & 0o777, 0o600)
        for api in ("https://another.invalid", "http://api-dev.yukon.org", "https://api-dev.yukon.org/path"):
            with self.assertRaises(CatalystError):
                configure_yukon_login(auth_path, api, worker_path)
        self.assertEqual(read_json(auth_path), saved)

    def test_client_prefers_yukon_key_and_does_not_send_it_to_http_host(self):
        with patch.dict(os.environ, {"CATALYST_API_TOKEN": "stale-password"}):
            self.assertEqual(solver_token(), KEY)
        with self.assertRaises(CatalystError):
            solver_fetch("http://untrusted.invalid", "/evaluations", KEY)
        self.assertEqual(self.upstream.call_count, 0)
