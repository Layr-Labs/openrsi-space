"""Real signed OIDC tokens and HTTP retrieval; no model calls or remote writes."""
import copy
from contextlib import redirect_stdout
import hashlib
from http.server import ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import uuid

from cryptography.hazmat.primitives.asymmetric import rsa
import jwt

from catalyst.common import CatalystError, read_json, write_json
from catalyst.evaluator import JobStore, handler_for
from catalyst.github_identity import AUDIENCE, GitHubIdentity, ISSUER
from catalyst.hosted import ServiceIdentity, configure_github
from catalyst.problems import initial_problems
from catalyst.receipts import PROTOCOL, check_receipt, problem_identity
from catalyst.remote import HTTPFailure, request_body, verification_reference
from test_yukon import completed

ROOT = Path(__file__).resolve().parents[1]


class GitHubReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = JobStore(self.root / "service")
        self.owner, self.benchmark, self.submission = [str(uuid.uuid4()) for _ in range(3)]
        with patch.dict("os.environ", {"CATALYST_LOCAL_TEST": "", "CATALYST_LOCAL_ECDSA": ""}):
            request = {**request_body(ROOT / "harnesses/ecdsa-baseline", "http://127.0.0.1:8778"),
                       "request_id": str(uuid.uuid4())}
        self.evaluation = self.store.create(self.owner, request)
        self.store.claim()
        self.store.transition(self.evaluation, "running")
        self.store.transition(self.evaluation, "verifying")
        result = completed(request, self.evaluation)
        self.store.transition(self.evaluation, "completed", result)
        self.reference = verification_reference(result, request)
        self.body = {"protocol": PROTOCOL, "reference": self.reference,
                     "problem": problem_identity(), "judge": request["judge"]}
        self.policy = {
            "enabled": True, "repository": "example/catalyst",
            "workflow": ".github/workflows/benchmark.yml", "problem": problem_identity(),
            "yukon_api_url": "https://api-dev.yukon.org", "benchmark_id": self.benchmark,
            "baseline": {"binding_id": str(uuid.uuid4()), "ref": "refs/heads/yukon/baseline/" + "b" * 40,
                         "sha": "b" * 40, "owner_id": self.owner, "evaluation_id": self.evaluation},
        }
        self.api_reads = []
        self.api_submission = {"id": self.submission, "benchmarkId": self.benchmark,
                               "solverAccountId": self.owner, "status": "validating"}

        def get_json(base, route, token):
            self.api_reads.append((base, route))
            self.assertEqual(base, "https://api-dev.yukon.org")
            self.assertEqual(route, f"/api/submissions/{self.submission}")
            return {"submission": self.api_submission}

        self.auth = ServiceIdentity({"mode": "service", "tokens": {
            hashlib.sha256(b"solver-key").hexdigest(): {"kind": "yukon-solver", "owner": self.owner},
        }, "github": {"repositories": {"12345": self.policy}}})
        self.auth.github = GitHubIdentity(self.auth.config["github"],
            keys=SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=self.key.public_key())),
            get_json=get_json)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0),
            handler_for(self.store, self.auth, initial_problems(), "remote"))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def token(self, updates=None):
        now = int(time.time())
        ref = f"refs/heads/submissions/{self.submission}"
        claims = {"iss": ISSUER, "aud": AUDIENCE, "sub": f"repo:example/catalyst:ref:{ref}",
                  "iat": now, "nbf": now - 1, "exp": now + 300,
                  "repository_id": "12345", "repository": "example/catalyst",
                  "ref": ref, "sha": "a" * 40, "workflow_sha": "a" * 40,
                  "workflow_ref": f"example/catalyst/.github/workflows/benchmark.yml@{ref}",
                  "run_id": "42", "run_attempt": "1", "event_name": "workflow_dispatch"}
        claims.update(updates or {})
        return jwt.encode(claims, self.key, algorithm="RS256")

    def post(self, body=None, token=None):
        request = Request(self.url + "/verifications/retrieve",
            data=json.dumps(body or self.body).encode(),
            headers={"Authorization": "Bearer " + (token or self.token()), "Content-Type": "application/json"})
        try:
            with urlopen(request) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            with error:
                return error.code, json.load(error)

    def test_workflow_resolves_owner_from_stock_yukon_and_retrieves_without_execution(self):
        status, result = self.post()
        self.assertEqual(status, 200, result)
        self.assertEqual(result["judgment"]["scores"], [100, .25])
        self.assertEqual(result["artifact"]["sha256"], self.reference["source_digest"])
        self.assertEqual(result, self.post()[1])
        self.assertEqual(len(self.api_reads), 2)
        self.assertNotIn(self.owner, json.dumps(result))
        self.assertNotIn("archive_base64", json.dumps(result))
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM jobs").fetchone()[0], 1)

            self.assertEqual(db.execute("SELECT count(*) FROM github_retrievals").fetchone()[0], 1)
        validity = copy.deepcopy(self.body)
        validity["judge"]["fields"] = {"scores": False, "validity": True}
        status, result = self.post(validity)
        self.assertEqual(status, 200, result)
        self.assertNotIn("scores", result["judgment"])

    def test_copied_receipt_wrong_benchmark_or_cancelled_submission_cannot_publish(self):
        for field, value in [("solverAccountId", str(uuid.uuid4())),
                             ("benchmarkId", str(uuid.uuid4())), ("status", "cancelled")]:
            before = self.api_submission[field]
            self.api_submission[field] = value
            self.assertEqual(self.post()[0], 403, field)
            self.api_submission[field] = before
        self.assertEqual(self.post({**self.body, "owner_id": self.owner})[0], 400)
        self.assertEqual(self.post({**self.body, "problem": {"id": "another-task", "version": "old"}})[0], 409)
        forged = copy.deepcopy(self.body)
        forged["reference"]["source_digest"] = "f" * 64
        self.assertEqual(self.post(forged)[0], 409)

    def test_bad_oidc_signature_claims_and_disabled_repositories_fail_before_yukon_lookup(self):
        for update in [
            {"iss": "https://attacker.invalid"}, {"aud": "wrong"}, {"exp": int(time.time()) - 60},
            {"repository_id": "99999"}, {"repository": "attacker/fork"},
            {"event_name": "pull_request"}, {"workflow_sha": "c" * 40},
            {"workflow_ref": "example/catalyst/.github/workflows/evil.yml@refs/heads/main"},
            {"job_workflow_ref": "attacker/reusable.yml@main"},
        ]:
            self.assertIn(self.post(token=self.token(update))[0], (401, 403))
        wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        claims = jwt.decode(self.token(), options={"verify_signature": False})
        self.assertEqual(self.post(token=jwt.encode(claims, wrong_key, algorithm="RS256"))[0], 401)
        self.policy["enabled"] = False
        self.assertEqual(self.post()[0], 403)
        self.assertEqual(self.api_reads, [])

    def test_direct_job_workflow_identity_can_retrieve_the_existing_receipt(self):
        workflow = f"example/catalyst/.github/workflows/benchmark.yml@refs/heads/submissions/{self.submission}"
        for updates in (
            {"job_workflow_ref": workflow},
            {"job_workflow_ref": workflow, "job_workflow_sha": "a" * 40},
        ):
            status, result = self.post(token=self.token(updates))
            self.assertEqual(status, 200, result)
            self.assertEqual(result["judgment"]["scores"], [100, .25])

    def test_different_job_workflow_or_revision_fails_before_yukon_lookup(self):
        workflow = f"example/catalyst/.github/workflows/benchmark.yml@refs/heads/submissions/{self.submission}"
        for updates in (
            {"job_workflow_ref": "attacker/catalyst/.github/workflows/benchmark.yml@refs/heads/main"},
            {"job_workflow_ref": "example/catalyst/.github/workflows/other.yml@refs/heads/main"},
            {"job_workflow_ref": workflow, "job_workflow_sha": "b" * 40},
            {"job_workflow_sha": "b" * 40},
            {"job_workflow_ref": None},
            {"job_workflow_sha": ""},
        ):
            self.assertEqual(self.post(token=self.token(updates))[0], 403)
        self.assertEqual(self.api_reads, [])

    def test_auth_rejection_logs_reason_without_credentials_or_receipt(self):
        token = self.token({"repository_id": "99999"})
        with self.assertLogs("catalyst.evaluator", level="WARNING") as logs:
            self.assertEqual(self.post(token=token)[0], 403)
        text = "\n".join(logs.output)
        self.assertIn("Remote verification is not enabled for this repository.", text)
        self.assertNotIn(token, text)
        self.assertNotIn(self.reference["source_digest"], text)
        self.assertNotIn(self.evaluation, text)

    def test_baseline_is_pinned_and_never_invents_solver_ownership(self):
        ref = "refs/heads/yukon/baseline/" + "b" * 40
        baseline = {"ref": ref, "sha": "b" * 40, "workflow_sha": "b" * 40,
                    "workflow_ref": f"example/catalyst/.github/workflows/benchmark.yml@{ref}"}
        self.assertEqual(self.post(token=self.token(baseline))[0], 200)
        self.assertEqual(self.api_reads, [])
        self.assertEqual(self.post(token=self.token({
            **baseline, "ref": "refs/heads/main",
            "workflow_ref": "example/catalyst/.github/workflows/benchmark.yml@refs/heads/main"}))[0], 403)
        baseline.update(sha="c" * 40, workflow_sha="c" * 40)
        self.assertEqual(self.post(token=self.token(baseline))[0], 403)
        self.policy["baseline"]["evaluation_id"] = str(uuid.uuid4())
        baseline.update(sha="b" * 40, workflow_sha="b" * 40)
        self.assertEqual(self.post(token=self.token(baseline))[0], 403)

    def test_receipt_only_client_writes_yukon_artifact_and_clears_stale_scores(self):
        workspace = self.root / "workspace"
        write_json(workspace / "submission/verification.json", self.reference)
        with patch.dict("os.environ", {"CATALYST_EVALUATOR_URL": self.url, "YUKON_EVALUATION": ""}), \
                patch("catalyst.yukon.authentication", return_value=(self.token(), {"kind": "github-actions"})), \
                redirect_stdout(io.StringIO()):
            result = check_receipt(workspace)
            self.assertEqual(result["scores"], [100, .25])
            self.assertEqual(result, read_json(workspace / ".catalyst/yukon/score.json"))
            # No harness source or evaluation settings exist in this checkout.
            self.assertEqual(list((workspace / "submission").iterdir()), [workspace / "submission/verification.json"])
            self.api_submission["solverAccountId"] = str(uuid.uuid4())
            with self.assertRaises(CatalystError):
                check_receipt(workspace)
            self.assertFalse((workspace / ".catalyst/yukon/score.json").exists())

    def test_solver_preview_is_owner_only_and_does_not_create_publication(self):
        self.assertEqual(self.post(token="solver-key")[0], 200)
        with self.store.connect() as db:
            self.assertIsNone(db.execute(
                "SELECT name FROM sqlite_master WHERE name='github_retrievals'").fetchone())
        self.auth.config["tokens"][hashlib.sha256(b"solver-key").hexdigest()]["owner"] = str(uuid.uuid4())
        self.assertEqual(self.post(token="solver-key")[0], 403)

    def binding_fixture(self):
        from catalyst.yukon_binding import PROTOCOL
        self.auth.yukon = SimpleNamespace(api="https://api-dev.yukon.org")
        job_id, execution_id = str(uuid.uuid4()), str(uuid.uuid4())
        job = {
            "id": job_id, "kind": "submission_validation", "status": "running",
            "benchmarkId": self.benchmark, "submissionId": self.submission,
            "accountId": self.owner,
            "input": {"executionSubmissionId": execution_id, "sourceRef": "a" * 40,
                      "sourceUrl": "https://github.com/example/catalyst",
                      "submissionArchiveRef": "private-upstream-archive-never-store"},
        }
        original_get = self.auth.github.get_json

        def lookup(base, route, token):
            if route == f"/api/jobs/{job_id}":
                self.assertEqual(base, "https://api-dev.yukon.org")
                if token != "ykn_private_test_key":
                    from catalyst.evaluator import APIError
                    raise APIError(401, "Yukon rejected the key.")
                return {"job": job}
            return original_get(base, route, token)

        self.auth.github.get_json = lookup
        body = {"protocol": PROTOCOL, "job_id": job_id,
                "benchmark_id": self.benchmark, "reference": self.reference}
        return job, body

    def bind(self, body, key="ykn_private_test_key"):
        from catalyst.remote import fetch
        return json.loads(fetch(self.url + "/verifications/yukon-bind", key, document=body))

    def test_pareto_execution_maps_to_actual_submission_and_keeps_keys_private(self):
        job, body = self.binding_fixture()
        result = self.bind(body)
        self.assertEqual(self.bind(body), result)
        self.assertEqual(result["submission_id"], self.submission)
        ref = f"refs/heads/submissions/{job['input']['executionSubmissionId']}"
        token = self.token({"ref": ref,
                            "workflow_ref": f"example/catalyst/.github/workflows/benchmark.yml@{ref}"})
        status, judgment = self.post(token=token)
        self.assertEqual(status, 200, judgment)
        self.assertEqual(judgment["judgment"]["scores"], [100, .25])
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM github_execution_bindings").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM jobs").fetchone()[0], 1)
        for path in self.root.rglob("*"):
            if path.is_file():
                content = path.read_bytes()
                self.assertNotIn(b"ykn_private_test_key", content)
                self.assertNotIn(b"private-upstream-archive-never-store", content)
        self.api_submission["status"] = "cancelled"
        self.assertEqual(self.post(token=token)[0], 403)

    def test_job_binding_rejects_wrong_owner_benchmark_kind_source_and_credentials(self):
        job, body = self.binding_fixture()
        for field, value in [
            ("accountId", str(uuid.uuid4())), ("benchmarkId", str(uuid.uuid4())),
            ("kind", "benchmark_baseline"), ("status", "cancelled"), ("id", str(uuid.uuid4())),
        ]:
            before = job[field]
            job[field] = value
            with self.assertRaises(HTTPFailure):
                self.bind(body)
            job[field] = before
        for field, value in [
            ("sourceUrl", "https://github.com/attacker/catalyst"),
            ("sourceRef", "not-a-commit"), ("executionSubmissionId", "../evil"),
        ]:
            before = job["input"][field]
            job["input"][field] = value
            with self.assertRaises(HTTPFailure):
                self.bind(body)
            job["input"][field] = before
        for key in ("ykn_invalid_private_key", "solver-key"):
            with self.assertRaises(HTTPFailure):
                self.bind(body, key)
        forged = copy.deepcopy(body)
        forged["reference"]["source_digest"] = "f" * 64
        with self.assertRaises(HTTPFailure):
            self.bind(forged)
        with self.store.connect() as db:
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master "
                                         "WHERE name='github_execution_bindings'").fetchone())

    def test_job_binding_is_immutable_and_cannot_change_yukon_origin(self):
        job, body = self.binding_fixture()
        self.bind(body)
        job["submissionId"] = str(uuid.uuid4())
        with self.assertRaises(HTTPFailure) as raised:
            self.bind(body)
        self.assertEqual(raised.exception.status, 409)
        self.policy["yukon_api_url"] = "https://attacker.invalid"
        with patch.object(self.auth.github, "get_json") as lookup:
            with self.assertRaises(HTTPFailure) as raised:
                self.bind(body)
            self.assertEqual(raised.exception.status, 403)
            lookup.assert_not_called()

    def test_bound_workflow_rejects_different_receipt_before_owner_lookup(self):
        job, body = self.binding_fixture()
        self.bind(body)
        ref = f"refs/heads/submissions/{job['input']['executionSubmissionId']}"
        token = self.token({"ref": ref,
                            "workflow_ref": f"example/catalyst/.github/workflows/benchmark.yml@{ref}"})
        forged = copy.deepcopy(self.body)
        forged["reference"]["source_digest"] = "f" * 64
        self.assertEqual(self.post(forged, token=token)[0], 403)
        self.assertEqual(self.api_reads, [])

    def test_stock_github_actions_manifest_and_workflow_contract(self):
        import yaml
        manifest = read_json(ROOT / "benchmark.json")
        self.assertEqual(manifest["runner"]["provider"], "github-actions")
        self.assertEqual(manifest["editablePaths"], ["submission/verification.json"])
        self.assertEqual(manifest["mode"], "pareto")
        workflow = yaml.safe_load((ROOT / ".github/workflows/benchmark.yml").read_text())
        # YAML 1.1 parses the key "on" as True.
        dispatch = workflow.get("on", workflow.get(True))["workflow_dispatch"]
        self.assertIn("yukon_evaluation", dispatch["inputs"])
        self.assertEqual(workflow["permissions"]["id-token"], "write")
        self.assertNotIn("pull_request", workflow.get("on", workflow.get(True)))

    def test_operator_configuration_preserves_credentials_and_baseline_identity(self):
        auth_file = self.root / "auth.json"
        write_json(auth_file, {"mode": "service", "tokens": {"hash": {"kind": "yukon-solver"}},
                              "grants": {"grant_example": {"owner": self.owner}}})
        args = dict(repository="example/catalyst", repository_id="12345",
                    yukon_api="https://api-dev.yukon.org", baseline_evaluation=self.evaluation,
                    baseline_sha="a" * 40)
        configure_github(self.store, auth_file, **args)
        first = read_json(auth_file)
        self.assertNotIn("benchmark_id", first["github"]["repositories"]["12345"])
        configure_github(self.store, auth_file, **args, benchmark_id=self.benchmark)
        second = read_json(auth_file)
        self.assertEqual(first["tokens"], second["tokens"])
        self.assertEqual(first["grants"], second["grants"])
        self.assertEqual(first["github"]["repositories"]["12345"]["baseline"],
                         second["github"]["repositories"]["12345"]["baseline"])
        self.assertEqual(second["github"]["repositories"]["12345"]["benchmark_id"], self.benchmark)
        self.assertEqual(second["github"]["repositories"]["12345"]["baseline"]["ref"],
                         "refs/heads/yukon/baseline/" + "a" * 40)
        self.assertEqual(auth_file.stat().st_mode & 0o777, 0o600)

    @unittest.skipUnless(os.environ.get("CATALYST_STOCK_YUKON"), "optional stock Yukon CLI integration")
    def test_unmodified_yukon_cli_checks_receipt_without_harness_source(self):
        stock = Path(os.environ["CATALYST_STOCK_YUKON"]).resolve()
        self.assertTrue((stock / "apps/cli/src/yukon.ts").is_file())
        # Exercise stock Yukon's actual branch constructor, not a fixture guess.
        baseline = subprocess.run(
            ["bun", "-e", "import {baselineBranchName} from './src/execution/github-actions.ts';"
             "console.log(baselineBranchName('a'.repeat(40)))"],
            cwd=stock, capture_output=True, text=True, timeout=30)
        self.assertEqual(baseline.returncode, 0, baseline.stderr)
        self.assertEqual(baseline.stdout.strip(), "yukon/baseline/" + "a" * 40)
        workspace = self.root / "stock-cli"
        write_json(workspace / "submission/verification.json", self.reference)
        manifest = read_json(ROOT / "benchmark.json")
        manifest["benchmarkCommand"] = [sys.executable, "-m", "catalyst.cli", "yukon-run"]
        write_json(workspace / "benchmark.json", manifest)
        subprocess.run(["git", "init", "--quiet", str(workspace)], check=True)
        config = self.root / "cli-config"
        write_json(config / "yukon/config.json", {"telemetry": False, "traceCapture": False})
        env = {key: value for key, value in os.environ.items()
               if key in {"PATH", "HOME", "TMPDIR"}}
        env.update(CATALYST_EVALUATOR_URL=self.url, CATALYST_API_TOKEN="solver-key",
                   PYTHONPATH=str(ROOT / "src"), YUKON_CONFIG_DIR=str(config),
                   YUKON_API_URL="http://127.0.0.1:1")
        result = subprocess.run(["bun", str(stock / "apps/cli/src/yukon.ts"), "run"],
                                cwd=workspace, env=env, capture_output=True, text=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(read_json(workspace / ".catalyst/yukon/score.json")["scores"], [100, .25])
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM jobs").fetchone()[0], 1)

class GitHubWorkflowTests(unittest.TestCase):
    def test_oidc_failure_is_distinguished_from_verifier_failure(self):
        from catalyst.yukon import authentication
        with patch.dict(os.environ, {
            "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": "example/catalyst",
            "GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "42", "GITHUB_RUN_ATTEMPT": "1",
            "ACTIONS_ID_TOKEN_REQUEST_URL": "https://example.invalid/token",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "private-request-token",
        }), patch("catalyst.yukon.fetch", side_effect=HTTPFailure(403)):
            with self.assertRaisesRegex(CatalystError, r"GitHub OIDC token request failed \(HTTP 403\)"):
                authentication()

    def test_receipt_workflow_uses_https_oidc_without_solver_or_ssh_secrets(self):
        import yaml
        source = (ROOT / ".github/workflows/benchmark.yml").read_text()
        workflow = yaml.load(source, Loader=yaml.BaseLoader)
        self.assertIn("workflow_dispatch", workflow["on"])
        self.assertEqual(workflow["permissions"], {"contents": "read", "id-token": "write"})
        job = workflow["jobs"]["benchmark"]
        self.assertEqual(job["env"]["CATALYST_EVALUATOR_URL"], "https://35.92.254.142")
        for obsolete in ("CATALYST_SSH_", "secrets.", "github-tunnel", "CATALYST_API_TOKEN", "YUKON_API_TOKEN"):
            self.assertNotIn(obsolete, source)
        self.assertEqual([step["run"] for step in job["steps"] if "run" in step],
                         ["uv sync --frozen", "uv run --frozen catalyst yukon-run"])
        upload = next(step for step in job["steps"] if step.get("uses", "").startswith("actions/upload-artifact@"))
        manifest = read_json(ROOT / "benchmark.json")
        self.assertEqual(upload["with"]["path"], manifest["scorePath"])
        self.assertEqual(manifest["editablePaths"], ["submission/verification.json"])
