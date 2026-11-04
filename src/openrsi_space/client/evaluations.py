"""Resumable submission, polling, cancellation and retained artifact access."""
from openrsi_space.compatibility import ARTIFACT_PROTOCOL, DIAGNOSTICS_PROTOCOL
from openrsi_space.compatibility import environment as _environment
import base64
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.parse
import uuid
from openrsi_space.common import OpenRSIError, now, read_json, snapshot_directory, write_json
from openrsi_space.credentials import platform_access
from openrsi_space.contracts.harness import SOURCE_EXCLUDES, validate_execution
from openrsi_space.contracts.evaluation import validate_evaluation_config
from openrsi_space.contracts.results import (
    PROTOCOL, PENDING, TERMINAL, digest, judge_input, bound_result,
    judgment, verification_reference, evaluation_id,
)
from openrsi_space.contracts.accounting import evaluation_models, pricing_schedule
from openrsi_space.challenge.catalog import initial_problems
from .configuration import evaluation_config
from .state import request_lock, private_json, export_private_json
from . import transport

MAX_SOURCE_BYTES = 8 * 1024 * 1024

def request_body(submission: Path, base: str, *, judge=None, context=None,
                 evaluation_overrides=None, pricing=None, check_pricing=True, execution=None,
                 publication=None, problem_release=None) -> dict:
    from openrsi_space.publication import publication_choices
    publication = publication_choices(publication, require_public=True)
    config = evaluation_config(submission / "evaluation.json", evaluation_overrides,
                               pricing=pricing, check_pricing=check_pricing)
    from openrsi_space.credentials import require_active_models
    require_active_models(evaluation_models(config))
    snapshot, archive = source_snapshot(submission, execution)
    if snapshot["kind"] != "harness":
        raise OpenRSIError("Submission must contain an executable harness.")
    execution = snapshot["document"].get("execution")
    validate_execution(execution)
    if execution["dockerfile"] not in snapshot["files"]:
        raise OpenRSIError("Missing build recipe in harness source.")
    from .source_limits import measure, check, DEFAULT_EXPANDED_BYTES
    check(measure(snapshot, archive), DEFAULT_EXPANDED_BYTES, MAX_SOURCE_BYTES)
    problem_set, mode = initial_problems(release=problem_release), "remote"
    if _environment("OPENRSI_LOCAL_ECDSA") == "1":
        if _environment("OPENRSI_LOCAL_TEST") == "1":
            raise OpenRSIError("Choose OPENRSI_LOCAL_ECDSA or OPENRSI_LOCAL_TEST, not both.")
        if urllib.parse.urlsplit(base).hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise OpenRSIError("Local ECDSA evaluations require a loopback service.")
        mode = "local-ecdsa"
    if _environment("OPENRSI_LOCAL_TEST") == "1":
        if urllib.parse.urlsplit(base).hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise OpenRSIError("Local-test evaluations require a loopback service.")
        fixture_path = _environment("OPENRSI_LOCAL_PROBLEM_SET")
        if not fixture_path:
            raise OpenRSIError("Local-test mode requires OPENRSI_LOCAL_PROBLEM_SET.")
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


class RemoteClient:
    def __init__(self, state: Path, *, bearer=None):
        self.state = state.resolve()
        self.base = transport.endpoint()
        self.bearer = bearer if bearer is not None else transport.solver_token()

    def folder(self, identity):
        return self.state / "remote/evaluations" / evaluation_id(identity)

    def pending_path(self, body):
        name = digest({"base": self.base, "body": body}) + ".json"
        # Preserve uncertain requests created before the standalone client existed.
        legacy = self.state / "yukon/pending" / name
        return legacy if legacy.is_file() else self.state / "remote/pending" / name

    def submit(self, submission: Path, *, judge=None, model_token=None, evaluation_overrides=None,
               execution=None, publication=None, problem_release=None, local_check=None, auto_publication=None, _quote_retry=False):
        if os.environ.get("GITHUB_ACTIONS") == "true":
            raise OpenRSIError("GitHub Actions must retrieve an existing result through openrsi-space yukon-run.")
        submission = submission.resolve()
        body = request_body(submission, self.base, judge=judge, evaluation_overrides=evaluation_overrides,
                            check_pricing=False, execution=execution, publication=publication,
                            problem_release=problem_release)
        from openrsi_space.credentials import require_remote_models, decode_remote_access
        require_remote_models(evaluation_models(body['evaluation']))
        if local_check is not None:
            from .local_check import request_identity
            if local_check.get('request_identity') != request_identity(body):
                raise OpenRSIError('Submission changed after its local check; review it and retry.')
        quote_path = None
        try:
            validate_evaluation_config(body["evaluation"])
        except OpenRSIError:
            # Shape/provider checks have already passed; resolve new model prices
            # at the service before sending any model credential.
            quote_path = self.state / "remote/quotes" / (digest({"base": self.base, "body": body}) + ".json")
            with request_lock(quote_path):
                if quote_path.is_file():
                    body["pricing"] = read_json(quote_path)
                else:
                    reply = json.loads(transport.solver_fetch(self.base, "/pricing/quote", self.bearer,
                        document={"models": evaluation_models(body["evaluation"]),
                                  **({"funding": "platform"} if platform_access(body["evaluation"]) else {})}))
                    body["pricing"] = reply["pricing"]
                    validate_evaluation_config(body["evaluation"], pricing=body["pricing"])
                    private_json(quote_path, body["pricing"])
            validate_evaluation_config(body["evaluation"], pricing=body["pricing"])
        from openrsi_space.credentials import temporary_access
        if temporary_access(body["evaluation"]):
            decode_remote_access(body['evaluation'], model_token)
        elif model_token is not None:
            raise OpenRSIError("This access mode does not accept personal model credentials.")
        if platform_access(body['evaluation']):
            from .local_evidence import attach
            attach(self, body, local_check)
        pending = self.pending_path(body)
        with request_lock(pending):
            if pending.is_file():
                request = read_json(pending)
                if {k: v for k, v in request.items() if k != "request_id"} != body:
                    raise OpenRSIError("Saved evaluation request does not match the current source/configuration.")
            else:
                request = {**body, "request_id": str(uuid.uuid4())}
                private_json(pending, request)
            if auto_publication is not None:
                from .yukon_publication import prepare
                prepare(self, request, auto_publication)
            private = {"model_token": model_token} if model_token is not None else {}
            try:
                accepted = json.loads(transport.solver_fetch(self.base, "/evaluations", self.bearer,
                                                   document=request, **private))
            except transport.HTTPFailure as error:
                error.saved_request_id = transport.safe_uuid(request.get('request_id'))
                # Keep only the transport's allowlisted diagnostic projection, not
                # the raw response, source envelope, headers or model credential.
                local_id = transport.safe_uuid(request.get("request_id"))
                diagnostic = self.state / "remote/diagnostics" / ((local_id or pending.stem) + ".json")
                try:
                    private_json(diagnostic, {"schema_version": 1, "at": now(),
                        "request_id": local_id, "http_status": error.status,
                        "details": error.details})
                    error.diagnostic_path = diagnostic
                except OSError:
                    error.diagnostic_write_failed = True
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
                    raise OpenRSIError("Evaluator accepted a different operation key.")
                session_path = self.folder(identity) / "session.json"
                recorded_check = local_check
                if local_check is not None and local_check.get('status') == 'resuming' and session_path.is_file():
                    recorded_check = read_json(session_path).get('local_check', local_check)
                private_json(session_path, {
                    "base": self.base, "request": request, "submission": str(submission),
                    **({'automatic_publication': True} if auto_publication is not None else {}),
                    **({"evaluation_overrides": evaluation_overrides} if evaluation_overrides else {}),
                    **({"pricing_quote": str(quote_path)} if quote_path else {}),
                    **({"execution": execution} if execution else {}),
                    **({"local_check": recorded_check} if recorded_check is not None else {}),
                })
        if identity is None:
            return self.submit(submission, judge=judge, model_token=model_token,
                               evaluation_overrides=evaluation_overrides, execution=execution,
                               publication=publication, problem_release=problem_release,
                               local_check=local_check, auto_publication=auto_publication, _quote_retry=True)
        return {"evaluation_id": identity, "request_id": request["request_id"],
                "source_digest": body["source"]["digest"], "evidence_mode": body["evidence_mode"],
                **({"publication": {"state": "pending", "benchmark_id": auto_publication['benchmark_id']}}
                   if auto_publication is not None else {})}

    def session(self, identity):
        path = self.folder(identity) / "session.json"
        if not path.is_file():
            raise OpenRSIError("Unknown local evaluation; use the same --state directory that submitted it.")
        session = read_json(path)
        if session["base"] != self.base:
            raise OpenRSIError("Evaluator transport.endpoint differs from the saved evaluation.")
        return session

    def status(self, identity):
        session = self.session(identity)
        result = json.loads(transport.solver_fetch(self.base, f"/evaluations/{identity}", self.bearer))
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

    def diagnostics(self, identity, output=None):
        identity = evaluation_id(identity)
        result = json.loads(transport.solver_fetch(
            self.base, f"/evaluations/{identity}/diagnostics", self.bearer))
        if (not isinstance(result, dict) or result.get("protocol") != DIAGNOSTICS_PROTOCOL
                or result.get("evaluation_id") != identity or result.get("scoring_evidence") is not False):
            raise OpenRSIError("Diagnostic report does not match this evaluation.")
        if output is not None:
            export_private_json(Path(output).expanduser().absolute(), result)
        return result

    def logs(self, identity, output):
        """Download sanitized owner logs; never print harness-controlled text."""
        import io
        import zipfile
        identity = evaluation_id(identity)
        data = transport.solver_fetch(self.base, f"/evaluations/{identity}/logs", self.bearer,
                                      limit=65 * 1024**2)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            info = archive.getinfo("manifest.json")
            if info.file_size > 16384:
                raise OpenRSIError("Oversized log manifest.")
            report = json.loads(archive.read(info))
            if (report.get("protocol") != "openrsi-harness-logs-v1"
                    or report.get("evaluation_id") != identity or report.get("sanitized") is not True
                    or report.get("scoring_evidence") is not False):
                raise OpenRSIError("Log report does not match this evaluation.")
        import tempfile
        target = Path(output).expanduser().absolute()
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
                temporary = Path(stream.name)
                os.fchmod(stream.fileno(), 0o600)
                stream.write(data)
            temporary.replace(target)
        finally:
            if temporary is not None: temporary.unlink(missing_ok=True)
        return {"evaluation_id": identity, "output": str(target), "coverage": report["coverage"]}

    def cancel(self, identity):
        identity = evaluation_id(identity)
        result = json.loads(transport.solver_fetch(
            self.base, f"/evaluations/{identity}/cancel", self.bearer, document={}))
        if result.get("evaluation_id") != identity:
            raise OpenRSIError("Cancellation response does not match this evaluation.")
        if (self.folder(identity) / "session.json").is_file():
            session = self.session(identity)
            bound_result(result, session["request"], identity)
            if result["status"] in TERMINAL:
                private_json(self.folder(identity) / "result.json", result)
                self.clear_pending(session)
        return {key: result[key] for key in (
            "evaluation_id", "status", "cancellation_requested", "trace_available", "reason"
        ) if key in result}

    def wait(self, identity):
        from openrsi_space.progress import progress_line, diagnostic_lines
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
                if result["status"] in TERMINAL:
                    for line in diagnostic_lines(result):
                        print(line, file=sys.stderr, flush=True)
                    if result["status"] != "completed":
                        self.clear_pending(session)
                        reason = result.get("reason")
                        reason = reason[:2048] if isinstance(reason, str) and reason else "No reason supplied."
                        # The remote response is untrusted terminal text.
                        raise OpenRSIError(f"Remote evaluation {result['status']}; reason: "
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
            raise OpenRSIError("Submission changed during evaluation; its original result is retained in remote state.")
        reference = read_json(self.folder(identity) / "verification.json")
        write_json(submission / "verification.json", reference)
        return submission / "verification.json"

    def artifacts(self, identity):
        identity = evaluation_id(identity)
        document = json.loads(transport.solver_fetch(
            self.base, f"/evaluations/{identity}/artifacts", self.bearer))
        if document.get("protocol") != ARTIFACT_PROTOCOL or document.get("evaluation_id") != identity:
            raise OpenRSIError("Artifact manifest does not match this evaluation.")
        return document

    def download_artifact(self, identity, kind, output):
        identity = evaluation_id(identity)
        if kind != "harness":
            raise OpenRSIError("Only harness source can be downloaded. Traces are retained internally.")
        manifest = self.artifacts(identity)
        expected = manifest["artifacts"][kind]
        descriptor = json.loads(transport.solver_fetch(
            self.base, f"/evaluations/{identity}/artifacts/{kind}", self.bearer))
        if any(descriptor.get(k) != expected.get(k) for k in ("sha256", "bytes", "media_type")):
            raise OpenRSIError("Download descriptor does not match the artifact manifest.")
        size, sha = descriptor["bytes"], descriptor["sha256"]
        if (type(size) is not int or not 0 < size <= 512 * 1024 * 1024
                or not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha)):
            raise OpenRSIError("Invalid artifact size or checksum.")
        options = {"limit": size, "output": output, "expected_sha256": sha, "expected_size": size}
        url = descriptor["url"]
        local = f"/evaluations/{identity}/artifacts/{kind}/content"
        if url == local:
            transport.solver_fetch(self.base, local, self.bearer, **options)
        else:
            parts = urllib.parse.urlsplit(url)
            if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.fragment:
                raise OpenRSIError("Artifact object downloads require HTTPS.")
            transport.fetch(url, "", **options)  # Never forward the solver's credential to object storage.
        return {"evaluation_id": identity, "kind": kind, "sha256": sha,
                "bytes": size, "path": str(Path(output).resolve())}

    def sharing(self, identity, changes=None):
        identity = evaluation_id(identity)
        route = f"/evaluations/{identity}/sharing"
        body = {"protocol": ARTIFACT_PROTOCOL, **changes} if changes is not None else None
        result = json.loads(transport.solver_fetch(self.base, route, self.bearer, document=body))
        if result.get("harness") or result.get("traces"):
            result["public_manifest"] = self.base + f"/public/evaluations/{identity}/artifacts"
            result["public_page"] = self.base + f"/public/evaluations/{identity}"
        return result
