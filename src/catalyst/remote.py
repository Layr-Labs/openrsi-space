"""Reusable verification-service client for Catalyst and the Yukon adapter."""
from __future__ import annotations

import base64
from contextlib import contextmanager
import fcntl
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from .common import (
    CatalystError, canonical, read_json, snapshot_directory, write_json,
)
from .executable import IMAGE_RE, SOURCE_EXCLUDES, validate_execution
from .problems import initial_problems
from .tiers import SCORING, VALIDITY, credit_limit, model_prices, pricing_schedule, project_observation

PROTOCOL = "catalyst-evaluation-v3"
MAX_SOURCE_BYTES = 8 * 1024 * 1024
PENDING = {"queued", "building", "running", "verifying"}
TERMINAL = {"completed", "failed", "cancelled"}


def digest(document) -> str:
    return hashlib.sha256(canonical(document)).hexdigest()



def judge_input(value: str | None) -> dict:
    default = {"policies": {"scoring": SCORING, "validity": VALIDITY},
               "fields": {"scores": True, "validity": True}}
    document = json.loads(value) if value else default
    if not isinstance(document, dict) or document.get("policies") != default["policies"]:
        raise CatalystError("Unsupported Catalyst evaluation policies.")
    fields = document.get("fields")
    if (not isinstance(fields, dict) or set(fields) != {"scores", "validity"}
            or any(type(item) is not bool for item in fields.values())
            or not any(fields.values())):
        raise CatalystError("Invalid requested evaluation fields.")
    return {"policies": default["policies"], "fields": fields}



def evaluation_config(path: Path) -> dict:
    return validate_evaluation_config(read_json(path))



def validate_evaluation_config(config: dict) -> dict:
    if (not isinstance(config, dict)
            or set(config) != {"schema_version", "llm_access", "model", "max_model_credits", "limits"}
            or type(config["schema_version"]) is not int or config["schema_version"] != 3):
        raise CatalystError("evaluation.json v3 requires llm_access, model, max_model_credits and limits.")
    access = config["llm_access"]
    if (not isinstance(access, dict) or set(access) != {"grant_id"}
            or not isinstance(access["grant_id"], str)
            or not re.fullmatch(r"grant_[A-Za-z0-9_-]{8,100}", access["grant_id"])):
        raise CatalystError("Set llm_access.grant_id to a private evaluator grant reference; never include a token.")
    model = config["model"]
    if (not isinstance(model, dict) or set(model) != {"provider", "name"}
            or any(not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9._/-]{1,120}", value)
                   for value in model.values())):
        raise CatalystError("model requires a provider and exact model name.")
    model_prices(model)
    credit_limit(config["max_model_credits"])
    limits = config["limits"]
    if not isinstance(limits, dict) or set(limits) != {"max_model_tokens", "max_seconds"}:
        raise CatalystError("limits requires max_model_tokens and max_seconds.")
    for key in ("max_model_tokens", "max_seconds"):
        if type(limits[key]) is not int or limits[key] <= 0:
            raise CatalystError(f"{key} must be a positive integer.")
    return config



class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise CatalystError("Evaluator redirects are refused to protect authorization.")



def fetch(url: str, token: str, *, document=None, limit=4 * 1024 * 1024) -> bytes:
    request = urllib.request.Request(
        url, data=canonical(document) if document is not None else None,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST" if document is not None else "GET",
    )
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
            content = response.read(limit + 1)
    except urllib.error.HTTPError as error:
        # Bodies may contain provider details; never echo them or authorization.
        status = error.code
        error.close()
        raise CatalystError(f"Evaluator returned HTTP {status}; request remains resumable.") from None
    except (urllib.error.URLError, http.client.HTTPException, OSError):
        raise CatalystError("Evaluator is unreachable; request remains resumable.") from None
    if len(content) > limit:
        raise CatalystError("Evaluator response exceeds the allowed size.")
    return content



def endpoint() -> str:
    value = os.environ.get("CATALYST_EVALUATOR_URL", "").rstrip("/")
    parts = urllib.parse.urlsplit(value)
    if (not parts.hostname or parts.username or parts.password or parts.query or parts.fragment
            or (parts.scheme != "https"
                and not (parts.scheme == "http" and parts.hostname in {"127.0.0.1", "localhost", "::1"}))):
        raise CatalystError("Configure CATALYST_EVALUATOR_URL as the trusted HTTPS evaluator endpoint.")
    return value



def bound_result(result: dict, request: dict, evaluation_id: str, *, original_request=True) -> None:
    expected = {
        "protocol": PROTOCOL, "evaluation_id": evaluation_id,
        "source_digest": request["source"]["digest"],
        "evaluation_config_digest": digest(request["evaluation"]),
        "problem_set_digest": digest(request["problem_set"]),
        "policies_digest": digest(request["judge"]["policies"]),
        "pricing_digest": digest(request["pricing"]),
    }
    if original_request:
        expected["request_id"] = request["request_id"]
    if "evidence_mode" in request:
        expected["evidence_mode"] = request["evidence_mode"]
    if (not isinstance(result, dict) or any(result.get(key) != value for key, value in expected.items())
            or result.get("status") not in PENDING | TERMINAL):
        raise CatalystError("Remote result does not match this evaluation request.")



def judgment(result: dict, request: dict) -> dict:
    """Project only trusted, bound observations into Yukon's public artifact."""
    if result.get("status") != "completed":
        raise CatalystError("Remote evaluation did not complete; no score is published.")
    if (result.get("evidence_mode") in {"local-test", "local-ecdsa"}
            and request.get("evidence_mode") != result["evidence_mode"]):
        raise CatalystError("Local-test or local ECDSA evidence cannot be used as a hosted evaluation.")
    if type(result.get("valid")) is not bool or not isinstance(result.get("reason"), str):
        raise CatalystError("Remote evaluator omitted its validity judgment.")
    if result.get("trace_available") is not True:
        raise CatalystError("Remote evaluator did not retain evaluation traces.")
    built = result.get("build")
    if (not isinstance(built, dict) or not isinstance(built.get("id"), str) or not built["id"]
            or not isinstance(built.get("image_digest"), str) or not IMAGE_RE.fullmatch(built["image_digest"])):
        raise CatalystError("Remote evaluator omitted the immutable build/image identity.")
    observations = result.get("observations")
    if not isinstance(observations, list):
        raise CatalystError("Remote evaluator omitted problem observations.")
    public, scores, seen = [], [], set()
    for observation in observations:
        if not isinstance(observation, dict):
            raise CatalystError("Malformed remote observation.")
        identity = observation.get("problem_id")
        problem = next((p for p in request["problem_set"] if p["id"] == identity), None)
        if (not problem or identity in seen
                or observation.get("problem_commit") != problem["repository"]["commit"]):
            raise CatalystError("Remote observation has a wrong or duplicate problem binding.")
        seen.add(identity)
        config = request["evaluation"]
        projected = project_observation(observation, config["model"], config["max_model_credits"], config["limits"])
        public.append({"problem_id": identity, "problem_commit": observation["problem_commit"], **projected})
    if result["valid"]:
        if seen != {p["id"] for p in request["problem_set"]}:
            raise CatalystError("Valid evaluation must independently verify ecdsa.fail.")
        best = public[0]["best"]
        if best is None:
            raise CatalystError("Valid scored evaluation has no verified candidate.")
        # A finite two-value adapter for Yukon. Missing tier measurements stay
        # explicit in metadata, never padded with invented scores or sentinels.
        scores = [best["performance"], best["normalized_model_usd"]]
    elif not result["reason"].strip():
        raise CatalystError("Invalid evaluation requires an explanation.")
    fields = request["judge"]["fields"]
    artifact = {"metrics": {
        "evaluationId": result["evaluation_id"], "sourceDigest": request["source"]["digest"],
        "buildId": built["id"], "imageDigest": built["image_digest"],
        "model": request["evaluation"]["model"], "observations": public,
        "problemSetDigest": digest(request["problem_set"]),
        "evaluationConfigDigest": digest(request["evaluation"]),
        "pricingDigest": digest(request["pricing"]),
        "maxModelCredits": request["evaluation"]["max_model_credits"],
        "limits": request["evaluation"]["limits"],
        "evidenceMode": result.get("evidence_mode", "remote"),
    }}
    if result.get("model_access") in {"disabled", "mock", "metered"}:
        artifact["metrics"]["modelAccess"] = result["model_access"]
    if fields["scores"]:
        artifact["scores"] = scores if result["valid"] else None
    if fields["validity"]:
        artifact.update(valid=result["valid"], reason=result["reason"][:2000])
    return artifact



def download_traces(base: str, bearer: str, evaluation_id: str, folder: Path) -> None:
    content = fetch(f"{base}/evaluations/{evaluation_id}/traces", bearer, limit=64 * 1024 * 1024)
    # Store privately, never unpack or execute archive content.
    target = folder / "traces.zip"
    temporary = folder / "traces.zip.tmp"
    temporary.write_bytes(content)
    temporary.chmod(0o600)
    temporary.replace(target)
    print(f"Private remote traces: {target}", file=sys.stderr, flush=True)



@contextmanager
def request_lock(pending_path: Path):
    pending_path.parent.mkdir(parents=True, exist_ok=True)
    with pending_path.with_suffix(".lock").open("a") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise CatalystError("This evaluation request is already running in another client.") from None
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)



def verification_reference(result: dict, body: dict) -> dict:
    return {
        "schema_version": 2, "evaluation_id": result["evaluation_id"],
        "source_digest": body["source"]["digest"],
        "evaluation_config_digest": digest(body["evaluation"]),
        "problem_set_digest": digest(body["problem_set"]),
        "policies_digest": digest(body["judge"]["policies"]),
        "pricing_digest": digest(body["pricing"]),
        "image_digest": result["build"]["image_digest"],
        "evidence_mode": body.get("evidence_mode", "remote"),
    }


def solver_token() -> str:
    bearer = (os.environ.get("CATALYST_API_TOKEN") or os.environ.get("YUKON_API_TOKEN")
              or os.environ.get("HILBERT_API_TOKEN") or os.environ.get("SUPABASE_ACCESS_TOKEN"))
    if not bearer:
        config_root = Path(os.environ.get("YUKON_CONFIG_DIR", str(Path.home() / ".config")))
        config_path = config_root / "yukon/config.json"
        if not config_path.exists() and not os.environ.get("YUKON_CONFIG_DIR"):
            config_path = config_root / "hilbert/config.json"
        config = read_json(config_path) if config_path.is_file() else {}
        bearer = config.get("token")
    if not isinstance(bearer, str) or not bearer or "\n" in bearer or "\r" in bearer:
        raise CatalystError("Set CATALYST_API_TOKEN or log in with yukon login before requesting an evaluation.")
    return bearer


def request_body(submission: Path, base: str, *, judge=None, context=None) -> dict:
    config = evaluation_config(submission / "evaluation.json")
    snapshot, archive = snapshot_directory(submission, exclude=SOURCE_EXCLUDES)
    if snapshot["kind"] != "harness":
        raise CatalystError("Submission must contain an executable harness.")
    execution = snapshot["document"].get("execution")
    validate_execution(execution)
    if execution["dockerfile"] not in snapshot["files"] or len(archive) > MAX_SOURCE_BYTES:
        raise CatalystError("Missing build recipe or source exceeds the 8 MiB submission limit.")
    problem_set, mode = initial_problems(), "remote"
    if os.environ.get("CATALYST_LOCAL_ECDSA") == "1":
        if os.environ.get("CATALYST_LOCAL_TEST") == "1":
            raise CatalystError("Choose CATALYST_LOCAL_ECDSA or CATALYST_LOCAL_TEST, not both.")
        if urllib.parse.urlsplit(base).hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise CatalystError("Local ECDSA evaluations require a loopback service.")
        mode = "local-ecdsa"
    if os.environ.get("CATALYST_LOCAL_TEST") == "1":
        if urllib.parse.urlsplit(base).hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise CatalystError("Local-test evaluations require a loopback service.")
        fixture_path = os.environ.get("CATALYST_LOCAL_PROBLEM_SET")
        if not fixture_path:
            raise CatalystError("Local-test mode requires CATALYST_LOCAL_PROBLEM_SET.")
        problem_set, mode = read_json(Path(fixture_path)), "local-test"
    return {"protocol": PROTOCOL,
            "source": {"digest": snapshot["version"], "archive_base64": base64.b64encode(archive).decode()},
            "evaluation": config, "problem_set": problem_set, "pricing": pricing_schedule(),
            "evidence_mode": mode, "judge": judge if judge is not None else judge_input(None),
            "context": context if context is not None else {"kind": "yukon-solver"}}


def evaluation_id(value):
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise CatalystError("Expected a canonical evaluation UUID.") from None
    return value


def private_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    write_json(path, value)
    path.chmod(0o600)


class RemoteClient:
    def __init__(self, state: Path, *, bearer=None):
        self.state = state.resolve()
        self.base = endpoint()
        self.bearer = bearer if bearer is not None else solver_token()

    def folder(self, identity):
        return self.state / "remote/evaluations" / evaluation_id(identity)

    def pending_path(self, body):
        name = digest({"base": self.base, "body": body}) + ".json"
        # Preserve uncertain requests created before the standalone client existed.
        legacy = self.state / "yukon/pending" / name
        return legacy if legacy.is_file() else self.state / "remote/pending" / name

    def submit(self, submission: Path, *, judge=None):
        if os.environ.get("GITHUB_ACTIONS") == "true":
            raise CatalystError("GitHub Actions must retrieve an existing result through catalyst yukon-run.")
        submission = submission.resolve()
        body = request_body(submission, self.base, judge=judge)
        pending = self.pending_path(body)
        with request_lock(pending):
            if pending.is_file():
                request = read_json(pending)
                if {k: v for k, v in request.items() if k != "request_id"} != body:
                    raise CatalystError("Saved evaluation request does not match the current source/configuration.")
            else:
                request = {**body, "request_id": str(uuid.uuid4())}
                private_json(pending, request)
            accepted = json.loads(fetch(f"{self.base}/evaluations", self.bearer, document=request))
            identity = evaluation_id(accepted.get("evaluation_id") if isinstance(accepted, dict) else None)
            if accepted.get("request_id") != request["request_id"]:
                raise CatalystError("Evaluator accepted a different operation key.")
            private_json(self.folder(identity) / "session.json", {
                "base": self.base, "request": request, "submission": str(submission),
            })
        return {"evaluation_id": identity, "request_id": request["request_id"],
                "source_digest": body["source"]["digest"], "evidence_mode": body["evidence_mode"]}

    def session(self, identity):
        path = self.folder(identity) / "session.json"
        if not path.is_file():
            raise CatalystError("Unknown local evaluation; use the same --state directory that submitted it.")
        session = read_json(path)
        if session["base"] != self.base:
            raise CatalystError("Evaluator endpoint differs from the saved evaluation.")
        return session

    def status(self, identity):
        session = self.session(identity)
        result = json.loads(fetch(f"{self.base}/evaluations/{identity}", self.bearer))
        bound_result(result, session["request"], identity)
        if result["status"] in TERMINAL:
            private_json(self.folder(identity) / "result.json", result)
        return result

    def clear_pending(self, session):
        body = {k: v for k, v in session["request"].items() if k != "request_id"}
        pending = self.pending_path(body)
        with request_lock(pending):
            if pending.is_file() and read_json(pending) == session["request"]:
                pending.unlink()

    def wait(self, identity):
        folder = self.folder(identity)
        session = self.session(identity)
        previous = None
        with request_lock(folder / "wait.json"):
            while True:
                result = self.status(identity)
                if result["status"] != previous:
                    print(f"Remote status: {result['status']}", file=sys.stderr, flush=True)
                    previous = result["status"]
                if result["status"] in TERMINAL:
                    if result.get("trace_available") is True and not (folder / "traces.zip").is_file():
                        download_traces(self.base, self.bearer, identity, folder)
                    if result["status"] != "completed":
                        self.clear_pending(session)
                        raise CatalystError(f"Remote evaluation {result['status']}; retained details: {folder}")
                    artifact = judgment(result, session["request"])
                    private_json(folder / "judgment.json", artifact)
                    private_json(folder / "verification.json", verification_reference(result, session["request"]))
                    self.clear_pending(session)
                    return artifact
                time.sleep(5)

    def export_reference(self, identity, submission=None):
        session = self.session(identity)
        submission = Path(submission).resolve() if submission is not None else Path(session["submission"])
        snapshot, _ = snapshot_directory(submission, exclude=SOURCE_EXCLUDES)
        if (snapshot["version"] != session["request"]["source"]["digest"]
                or evaluation_config(submission / "evaluation.json") != session["request"]["evaluation"]):
            raise CatalystError("Submission changed during evaluation; its original result is retained in remote state.")
        reference = read_json(self.folder(identity) / "verification.json")
        write_json(submission / "verification.json", reference)
        return submission / "verification.json"

    def traces(self, identity):
        result = self.status(identity)
        if result.get("trace_available") is not True:
            raise CatalystError("Remote traces are not available yet.")
        folder = self.folder(identity)
        download_traces(self.base, self.bearer, identity, folder)
        return folder / "traces.zip"
