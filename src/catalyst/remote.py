"""Reusable verification-service client for Catalyst and the Yukon adapter."""
from __future__ import annotations

import base64
import copy
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
from .tiers import (
    LEGACY_VALIDITY, SCORING, VALIDITY, credit_limit, evaluation_models,
    model_prices, pricing_schedule, project_observation,
)

PROTOCOL = "catalyst-evaluation-v3"
MAX_SOURCE_BYTES = 8 * 1024 * 1024
PENDING = {"queued", "awaiting_credentials", "building", "running", "verifying"}
TERMINAL = {"completed", "failed", "cancelled"}


def digest(document) -> str:
    return hashlib.sha256(canonical(document)).hexdigest()



def judge_input(value: str | None) -> dict:
    default = {"policies": {"scoring": SCORING, "validity": VALIDITY},
               "fields": {"scores": True, "validity": True}}
    document = json.loads(value) if value else default
    supported = [default["policies"], {"scoring": SCORING, "validity": LEGACY_VALIDITY}]
    if not isinstance(document, dict) or document.get("policies") not in supported:
        raise CatalystError("Unsupported Catalyst evaluation policies.")
    fields = document.get("fields")
    if (not isinstance(fields, dict) or set(fields) != {"scores", "validity"}
            or any(type(item) is not bool for item in fields.values())
            or not any(fields.values())):
        raise CatalystError("Invalid requested evaluation fields.")
    return {"policies": document["policies"], "fields": fields}



def evaluation_config(path: Path, overrides: dict | None = None, *, check_pricing=True, pricing=None) -> dict:
    """Resolve run settings independently of the submitted source bundle."""
    overrides = overrides or {}
    allowed = {"provider", "model", "reasoning_effort", "budget", "max_tokens", "max_seconds"}
    if set(overrides) - allowed:
        raise CatalystError("Unknown evaluation setting.")
    if path.is_file():
        config = copy.deepcopy(read_json(path))
        if not isinstance(config, dict):
            raise CatalystError("evaluation.json must be an object.")
    else:
        if not {"provider", "model", "budget"} <= set(overrides):
            raise CatalystError("Supply evaluation.json or --provider, --model and --budget.")
        config = {
            "schema_version": 3,
            "llm_access": {"grant_id": "grant_temporary_provider"},
            "model": {},
            "max_model_credits": overrides["budget"],
            "limits": {"max_model_tokens": 100000, "max_seconds": 900},
        }
    if ("provider" in overrides) != ("model" in overrides):
        raise CatalystError("Set --provider and --model together.")
    if {"provider", "model", "reasoning_effort"} & set(overrides):
        if config.get("schema_version") == 4:
            raise CatalystError("For a model ensemble, edit models in evaluation.json instead of model flags.")
        if "provider" in overrides:
            # Never carry provider-specific reasoning settings to another model.
            config["model"] = {"provider": overrides["provider"], "name": overrides["model"]}
        if "reasoning_effort" in overrides:
            if not isinstance(config.get("model"), dict):
                raise CatalystError("model must be an object.")
            config["model"]["reasoning_effort"] = overrides["reasoning_effort"]
    if "budget" in overrides:
        config["max_model_credits"] = overrides["budget"]
    for option, key in (("max_tokens", "max_model_tokens"), ("max_seconds", "max_seconds")):
        if option in overrides:
            if not isinstance(config.get("limits"), dict):
                raise CatalystError("limits must be an object.")
            config["limits"][key] = overrides[option]
    return validate_evaluation_config(config, check_pricing=check_pricing, pricing=pricing)



def validate_evaluation_config(config: dict, *, check_pricing=True, pricing=None) -> dict:
    version = config.get("schema_version") if isinstance(config, dict) else None
    if (not isinstance(config, dict)
            or set(config) != {"schema_version", "llm_access", "model", "max_model_credits", "limits"} | ({"models"} if version == 4 else set())
            or type(version) is not int or version not in (3, 4)):
        raise CatalystError("evaluation.json requires v3, or v4 with an explicit models list.")
    access = config["llm_access"]
    if (not isinstance(access, dict) or set(access) != {"grant_id"}
            or not isinstance(access["grant_id"], str)
            or not re.fullmatch(r"grant_[A-Za-z0-9_-]{8,100}", access["grant_id"])):
        raise CatalystError("Set llm_access.grant_id to a private evaluator grant reference; never include a token.")
    models = evaluation_models(config)
    if not isinstance(models, list) or not 1 <= len(models) <= 16 or config["model"] != models[0]:
        raise CatalystError("models must contain 1..16 entries, starting with the default model.")
    seen = set()
    for model in models:
        validate_model(model, check_pricing=check_pricing, pricing=pricing)
        key = (model["provider"], model["name"])
        if key in seen:
            raise CatalystError("Duplicate allowed model.")
        seen.add(key)
    credit_limit(config["max_model_credits"])
    limits = config["limits"]
    if not isinstance(limits, dict) or set(limits) != {"max_model_tokens", "max_seconds"}:
        raise CatalystError("limits requires max_model_tokens and max_seconds.")
    for key in ("max_model_tokens", "max_seconds"):
        if type(limits[key]) is not int or limits[key] <= 0:
            raise CatalystError(f"{key} must be a positive integer.")
    return config


def validate_model(model, *, check_pricing=True, pricing=None):
    if (not isinstance(model, dict) or (not {"provider", "name"} <= set(model) or set(model) - {"provider", "name", "reasoning_effort"})
            or any(not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9._/:-]{1,120}", value)
                   for value in model.values())):
        raise CatalystError("model requires a provider and exact model name.")
    if "reasoning_effort" in model and model["reasoning_effort"] not in {"low", "medium", "high", "xhigh", "max"}:
        raise CatalystError("Unsupported reasoning effort.")
    from .credentials import PROVIDERS
    if model["provider"] not in PROVIDERS:
        raise CatalystError("Provider requires an authentication/protocol adapter.")
    from .provider_profiles import PROFILES, upstream_model
    if model['provider'] in PROFILES:
        try:
            upstream_model(model['provider'], model['name'])
        except ValueError as error:
            raise CatalystError(str(error)) from None
    if check_pricing:
        model_prices(model, pricing)



class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise CatalystError("Evaluator redirects are refused to protect authorization.")



class HTTPFailure(CatalystError):
    def __init__(self, status):
        self.status = status
        super().__init__(f"Evaluator returned HTTP {status}; request remains resumable.")


def fetch(url: str, token: str, *, document=None, limit=4 * 1024 * 1024, timeout=30,
          model_token=None, output=None, expected_sha256=None, expected_size=None) -> bytes:
    private_headers = {}
    if model_token is not None:
        from .credentials import TOKEN_HEADER, validate_token
        validate_token(model_token)
        parts = urllib.parse.urlsplit(url)
        if (parts.scheme != "https" or parts.username or parts.password
                or parts.path != "/evaluations" or parts.query or parts.fragment):
            raise CatalystError("Provider tokens require the HTTPS evaluation endpoint.")
        private_headers[TOKEN_HEADER] = model_token
    request = urllib.request.Request(
        url, data=canonical(document) if document is not None else None,
        headers={**({"Authorization": f"Bearer {token}"} if token else {}),
                 "Content-Type": "application/json", **private_headers},
        method="POST" if document is not None else "GET",
    )
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            if output is None:
                content = response.read(limit + 1)
            else:
                import tempfile
                target = Path(output)
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = None
                try:
                    with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".artifact-", delete=False) as stream:
                        temporary = Path(stream.name)
                        hasher, size = hashlib.sha256(), 0
                        while chunk := response.read(1024 * 1024):
                            size += len(chunk)
                            if size > limit:
                                raise CatalystError("Artifact exceeds its declared download limit.")
                            hasher.update(chunk)
                            stream.write(chunk)
                    if size != expected_size or hasher.hexdigest() != expected_sha256:
                        raise CatalystError("Downloaded artifact does not match its verified checksum and size.")
                    temporary.replace(target)
                    temporary = None
                    return b""
                finally:
                    if temporary is not None:
                        temporary.unlink(missing_ok=True)
    except urllib.error.HTTPError as error:
        # Bodies may contain provider details; never echo them or authorization.
        status = error.code
        error.close()
        raise HTTPFailure(status) from None
    except (urllib.error.URLError, http.client.HTTPException, OSError):
        raise CatalystError("Evaluator is unreachable; request remains resumable.") from None
    if len(content) > limit:
        raise CatalystError("Evaluator response exceeds the allowed size.")
    return content


# Process-local only. Long-running clients renew automatically; restarting the
# client or server never requires a saved Catalyst password.
_solver_sessions = {}


def solver_fetch(base, route, bearer, *, document=None, limit=4 * 1024 * 1024, model_token=None,
                 output=None, expected_sha256=None, expected_size=None):
    private = {"model_token": model_token} if model_token is not None else {}
    if output is not None:
        private.update(output=output, expected_sha256=expected_sha256, expected_size=expected_size)
    if not bearer.startswith("ykn_"):
        return fetch(base + route, bearer, document=document, limit=limit, **private)
    parts = urllib.parse.urlsplit(base)
    if (parts.username or parts.password or parts.query or parts.fragment or not parts.hostname
            or (parts.scheme != "https" and not (
                parts.scheme == "http" and parts.hostname in {"127.0.0.1", "localhost", "::1"}))):
        raise CatalystError("Yukon login requires a trusted HTTPS evaluator endpoint.")
    cache_key = (base, hashlib.sha256(bearer.encode()).digest())
    for attempt in range(2):
        cached = _solver_sessions.get(cache_key)
        if cached is None or cached[1] <= time.monotonic():
            result = json.loads(fetch(base + "/auth/yukon", bearer,
                                      document={"protocol": "catalyst-yukon-session-v1"},
                                      limit=16 * 1024))
            if (not isinstance(result, dict) or result.get("protocol") != "catalyst-yukon-session-v1"
                    or not isinstance(result.get("access_token"), str)
                    or not re.fullmatch(r"cys_[A-Za-z0-9_.-]{1,4096}", result["access_token"])
                    or type(result.get("expires_in")) is not int
                    or not 60 <= result["expires_in"] <= 900):
                raise CatalystError("Evaluator returned an invalid login session.")
            evaluation_id(result.get("owner_id"))
            cached = (result["access_token"], time.monotonic() + result["expires_in"] - 30)
            if len(_solver_sessions) >= 8:
                _solver_sessions.clear()
            _solver_sessions[cache_key] = cached
        try:
            return fetch(base + route, cached[0], document=document, limit=limit, **private)
        except HTTPFailure as error:
            if error.status != 401 or attempt:
                raise
            # Authentication failed before dispatch (e.g. the server restarted).
            # Keep the same request body/operation key when renewing and retrying.
            _solver_sessions.pop(cache_key, None)



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
    judge = judge_input(json.dumps(request["judge"]))
    if result.get("status") != "completed":
        raise CatalystError("Remote evaluation did not complete; no score is published.")
    if (result.get("evidence_mode") in {"local-test", "local-ecdsa"}
            and request.get("evidence_mode") != result["evidence_mode"]):
        raise CatalystError("Local-test or local ECDSA evidence cannot be used as a hosted evaluation.")
    if type(result.get("valid")) is not bool or not isinstance(result.get("reason"), str):
        raise CatalystError("Remote evaluator omitted its validity judgment.")
    # This attests internal evidence retention, not a user download capability.
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
        projected = project_observation(observation, evaluation_models(config), config["max_model_credits"],
                                        config["limits"], request["pricing"],
                                        allow_inflight_overshoot=judge["policies"]["validity"] == VALIDITY)
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
        "models": evaluation_models(request["evaluation"]),
        "problemSetDigest": digest(request["problem_set"]),
        "evaluationConfigDigest": digest(request["evaluation"]),
        "pricingDigest": digest(request["pricing"]),
        "maxModelCredits": request["evaluation"]["max_model_credits"],
        "limits": request["evaluation"]["limits"],
        "evidenceMode": result.get("evidence_mode", "remote"),
    }}
    if result.get("model_access") in {"disabled", "mock", "metered"}:
        artifact["metrics"]["modelAccess"] = result["model_access"]
    if "source_audit" in result:
        audit = result["source_audit"]
        if (not isinstance(audit, dict)
                or set(audit) != {"policy", "digest", "config_digest", "model", "status"}
                or audit["digest"] != request["source"]["digest"]
                or audit["status"] != "passed"
                or any(not isinstance(audit[k], str) or not audit[k] for k in audit)):
            raise CatalystError("Source audit does not match a passed review of this harness.")
        artifact["metrics"]["sourceAudit"] = audit
    if fields["scores"]:
        artifact["scores"] = scores if result["valid"] else None
    if fields["validity"]:
        artifact.update(valid=result["valid"], reason=result["reason"][:2000])
    return artifact



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
    bearer = (os.environ.get("YUKON_API_TOKEN") or os.environ.get("CATALYST_API_TOKEN")
              or os.environ.get("HILBERT_API_TOKEN") or os.environ.get("SUPABASE_ACCESS_TOKEN"))
    if not bearer:
        config_root = Path(os.environ.get("YUKON_CONFIG_DIR", str(Path.home() / ".config")))
        config_path = config_root / "yukon/config.json"
        if not config_path.exists() and not os.environ.get("YUKON_CONFIG_DIR"):
            config_path = config_root / "hilbert/config.json"
        config = read_json(config_path) if config_path.is_file() else {}
        bearer = config.get("token")
    if not isinstance(bearer, str) or not bearer or "\n" in bearer or "\r" in bearer:
        raise CatalystError("Log in with yukon login or set YUKON_API_TOKEN before requesting an evaluation.")
    return bearer


def request_body(submission: Path, base: str, *, judge=None, context=None,
                 evaluation_overrides=None, pricing=None, check_pricing=True, execution=None,
                 publication=None) -> dict:
    from .publication import publication_choices
    publication = publication_choices(publication)
    config = evaluation_config(submission / "evaluation.json", evaluation_overrides,
                               pricing=pricing, check_pricing=check_pricing)
    snapshot, archive = source_snapshot(submission, execution)
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
            "evaluation": config, "problem_set": problem_set,
            "publication": publication,
            "pricing": pricing_schedule() if pricing is None else pricing,
            "evidence_mode": mode, "judge": judge if judge is not None else judge_input(None),
            "context": context if context is not None else {"kind": "yukon-solver"}}

def source_snapshot(submission, execution=None):
    document = None
    if execution is not None:
        validate_execution(execution)
        document = {"schema_version": 1, "kind": "harness", "id": "submitted-agent",
                    "title": "Submitted agent", "execution": execution}
    return snapshot_directory(submission, exclude=SOURCE_EXCLUDES, harness_document=document)


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

    def submit(self, submission: Path, *, judge=None, model_token=None, evaluation_overrides=None,
               execution=None, publication=None, _quote_retry=False):
        if os.environ.get("GITHUB_ACTIONS") == "true":
            raise CatalystError("GitHub Actions must retrieve an existing result through catalyst yukon-run.")
        submission = submission.resolve()
        body = request_body(submission, self.base, judge=judge, evaluation_overrides=evaluation_overrides,
                            check_pricing=False, execution=execution, publication=publication,
                            )
        quote_path = None
        try:
            validate_evaluation_config(body["evaluation"])
        except CatalystError:
            # Shape/provider checks have already passed; resolve new model prices
            # at the service before sending any model credential.
            quote_path = self.state / "remote/quotes" / (digest({"base": self.base, "body": body}) + ".json")
            with request_lock(quote_path):
                if quote_path.is_file():
                    body["pricing"] = read_json(quote_path)
                else:
                    reply = json.loads(solver_fetch(self.base, "/pricing/quote", self.bearer,
                        document={"models": evaluation_models(body["evaluation"])}))
                    body["pricing"] = reply["pricing"]
                    validate_evaluation_config(body["evaluation"], pricing=body["pricing"])
                    private_json(quote_path, body["pricing"])
            validate_evaluation_config(body["evaluation"], pricing=body["pricing"])
        from .credentials import temporary_access, validate_token
        if temporary_access(body["evaluation"]):
            validate_token(model_token)
        elif model_token is not None:
            raise CatalystError("Use grant_temporary_provider in evaluation.json for live model access.")
        pending = self.pending_path(body)
        with request_lock(pending):
            if pending.is_file():
                request = read_json(pending)
                if {k: v for k, v in request.items() if k != "request_id"} != body:
                    raise CatalystError("Saved evaluation request does not match the current source/configuration.")
            else:
                request = {**body, "request_id": str(uuid.uuid4())}
                private_json(pending, request)
            private = {"model_token": model_token} if model_token is not None else {}
            try:
                accepted = json.loads(solver_fetch(self.base, "/evaluations", self.bearer,
                                                   document=request, **private))
            except HTTPFailure as error:
                if error.status != 410 or quote_path is None or _quote_retry:
                    raise
                # 410 is an explicit service guarantee that this operation has
                # not been accepted. Unknown outcomes never reach this path.
                pending.unlink()
                quote_path.unlink(missing_ok=True)
                accepted = None
            if accepted is None:
                identity = None
            else:
                identity = evaluation_id(accepted.get("evaluation_id") if isinstance(accepted, dict) else None)
                if accepted.get("request_id") != request["request_id"]:
                    raise CatalystError("Evaluator accepted a different operation key.")
                private_json(self.folder(identity) / "session.json", {
                    "base": self.base, "request": request, "submission": str(submission),
                    **({"evaluation_overrides": evaluation_overrides} if evaluation_overrides else {}),
                    **({"pricing_quote": str(quote_path)} if quote_path else {}),
                    **({"execution": execution} if execution else {}),
                })
        if identity is None:
            return self.submit(submission, judge=judge, model_token=model_token,
                               evaluation_overrides=evaluation_overrides, execution=execution,
                               publication=publication, _quote_retry=True)
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
        result = json.loads(solver_fetch(self.base, f"/evaluations/{identity}", self.bearer))
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
            if session.get("pricing_quote"):
                Path(session["pricing_quote"]).unlink(missing_ok=True)

    def cancel(self, identity):
        identity = evaluation_id(identity)
        result = json.loads(solver_fetch(
            self.base, f"/evaluations/{identity}/cancel", self.bearer, document={}))
        if result.get("evaluation_id") != identity:
            raise CatalystError("Cancellation response does not match this evaluation.")
        if (self.folder(identity) / "session.json").is_file():
            session = self.session(identity)
            bound_result(result, session["request"], identity)
            if result["status"] in TERMINAL:
                private_json(self.folder(identity) / "result.json", result)
                self.clear_pending(session)
        return {key: result[key] for key in (
            "evaluation_id", "status", "cancellation_requested", "trace_available", "reason"
        ) if key in result}

    def renew_access(self, identity, token):
        identity = evaluation_id(identity)
        result = json.loads(solver_fetch(
            self.base, f"/evaluations/{identity}/credentials", self.bearer,
            document={}, model_token=token))
        if result.get("evaluation_id") != identity:
            raise CatalystError("Credential response does not match this evaluation.")
        return {"evaluation_id": identity, "status": result["status"]}

    def wait(self, identity):
        from .progress import progress_line
        folder = self.folder(identity)
        session = self.session(identity)
        previous = None
        started = time.monotonic()
        last_report = started
        with request_lock(folder / "wait.json"):
            while True:
                result = self.status(identity)
                current = time.monotonic()
                if result["status"] != previous or current - last_report >= 15:
                    print(progress_line(result, current - started), file=sys.stderr, flush=True)
                    previous = result["status"]
                    last_report = current
                if result["status"] == "awaiting_credentials":
                    raise CatalystError(
                        f"Temporary access expired or was lost on restart. Renew with "
                        f"catalyst remote renew-access {identity}, then resume remote wait.")
                if result["status"] in TERMINAL:
                    if result["status"] != "completed":
                        self.clear_pending(session)
                        reason = result.get("reason")
                        reason = reason[:2048] if isinstance(reason, str) and reason else "No reason supplied."
                        # The remote response is untrusted terminal text.
                        raise CatalystError(f"Remote evaluation {result['status']}; reason: "
                                            f"{json.dumps(reason, ensure_ascii=True)}; retained details: {folder}")
                    artifact = judgment(result, session["request"])
                    private_json(folder / "judgment.json", artifact)
                    private_json(folder / "verification.json", verification_reference(result, session["request"]))
                    self.clear_pending(session)
                    return artifact
                time.sleep(5)

    def export_reference(self, identity, submission=None):
        session = self.session(identity)
        submission = Path(submission).resolve() if submission is not None else Path(session["submission"])
        snapshot, _ = source_snapshot(submission, session.get("execution"))
        if (snapshot["version"] != session["request"]["source"]["digest"]
                or evaluation_config(submission / "evaluation.json", session.get("evaluation_overrides"),
                                     pricing=session["request"]["pricing"])
                != session["request"]["evaluation"]):
            raise CatalystError("Submission changed during evaluation; its original result is retained in remote state.")
        reference = read_json(self.folder(identity) / "verification.json")
        write_json(submission / "verification.json", reference)
        return submission / "verification.json"

    def artifacts(self, identity):
        identity = evaluation_id(identity)
        document = json.loads(solver_fetch(
            self.base, f"/evaluations/{identity}/artifacts", self.bearer))
        if document.get("protocol") != "catalyst-artifacts-v1" or document.get("evaluation_id") != identity:
            raise CatalystError("Artifact manifest does not match this evaluation.")
        return document

    def download_artifact(self, identity, kind, output):
        identity = evaluation_id(identity)
        if kind != "harness":
            raise CatalystError("Only harness source can be downloaded. Traces are retained internally.")
        manifest = self.artifacts(identity)
        expected = manifest["artifacts"][kind]
        descriptor = json.loads(solver_fetch(
            self.base, f"/evaluations/{identity}/artifacts/{kind}", self.bearer))
        if any(descriptor.get(k) != expected.get(k) for k in ("sha256", "bytes", "media_type")):
            raise CatalystError("Download descriptor does not match the artifact manifest.")
        size, sha = descriptor["bytes"], descriptor["sha256"]
        if (type(size) is not int or not 0 < size <= 512 * 1024 * 1024
                or not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha)):
            raise CatalystError("Invalid artifact size or checksum.")
        options = {"limit": size, "output": output, "expected_sha256": sha, "expected_size": size}
        url = descriptor["url"]
        local = f"/evaluations/{identity}/artifacts/{kind}/content"
        if url == local:
            solver_fetch(self.base, local, self.bearer, **options)
        else:
            parts = urllib.parse.urlsplit(url)
            if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.fragment:
                raise CatalystError("Artifact object downloads require HTTPS.")
            fetch(url, "", **options)  # Never forward the solver's credential to object storage.
        return {"evaluation_id": identity, "kind": kind, "sha256": sha,
                "bytes": size, "path": str(Path(output).resolve())}

    def sharing(self, identity, changes=None):
        identity = evaluation_id(identity)
        route = f"/evaluations/{identity}/sharing"
        body = {"protocol": "catalyst-artifacts-v1", **changes} if changes is not None else None
        result = json.loads(solver_fetch(self.base, route, self.bearer, document=body))
        if result.get("harness") or result.get("traces"):
            result["public_manifest"] = self.base + f"/public/evaluations/{identity}/artifacts"
            result["public_page"] = self.base + f"/public/evaluations/{identity}"
        return result
