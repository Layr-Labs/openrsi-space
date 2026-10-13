"""Persistent verification API with local fixtures or configured service identities.

The API never executes submitted source. A separate worker claims jobs from
SQLite. Authentication is supplied by the selected identity provider.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from pathlib import Path
import sqlite3
import uuid

from .common import CatalystError, canonical, now, open_bundle, read_json
from .executable import SOURCE_EXCLUDES, validate_execution
from .tiers import pricing_schedule
from .problems import initial_problems
from .remote import MAX_SOURCE_BYTES, PROTOCOL, digest, judge_input, validate_evaluation_config

BODY_LIMIT = 12 * 1024 * 1024


class APIError(CatalystError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def identity(value):
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise APIError(400, "Expected a canonical UUID.") from None
    return value


def bindings(request, evaluation_id):
    return {
        "protocol": PROTOCOL, "evaluation_id": evaluation_id, "request_id": request["request_id"],
        "source_digest": request["source"]["digest"],
        "evaluation_config_digest": digest(request["evaluation"]),
        "problem_set_digest": digest(request["problem_set"]),
        "policies_digest": digest(request["judge"]["policies"]),
        "pricing_digest": digest(request["pricing"]), "evidence_mode": request["evidence_mode"],
    }


class LocalIdentity:
    """Explicit local-only substitute for remote Yukon/OIDC authentication."""

    def __init__(self, config):
        if config.get("mode") != "local-test":
            raise CatalystError("Only local-test identity fixtures are supported.")
        self.config = config

    def authenticate(self, header):
        token = header[7:] if isinstance(header, str) and header.startswith("Bearer ") else ""
        hashed = hashlib.sha256(token.encode()).hexdigest()
        principal = self.config["tokens"].get(hashed)
        if not principal:
            raise APIError(401, "Authentication required.")
        return principal

    def authorize_run(self, principal, request):
        if principal["kind"] != "yukon-solver" or request["context"] != {"kind": "yukon-solver"}:
            raise APIError(403, "Only a solver can request an evaluation.")
        config = request["evaluation"]
        from .tiers import evaluation_models
        grant = self.config["grants"].get(config["llm_access"]["grant_id"])
        if (not grant or grant["owner"] != principal["owner"] or grant["model"] != config["model"]
                or evaluation_models(config) != evaluation_models(grant)
                or config["max_model_credits"] > grant["max_model_credits"]
                or any(config["limits"][key] > grant["limits"][key] for key in grant["limits"])):
            raise APIError(403, "The model grant does not authorize these evaluation limits.")

    def workflow_context(self, principal, context):
        if principal["kind"] != "github-actions" or context != principal["context"]:
            raise APIError(403, "Workflow identity does not match the authorized fixture.")

    def creation_limits(self):
        return None


def validate_request(request, problem_set, *, submission=False, evidence_mode="local-test",
                     pricing_validator=None):
    required = {"protocol", "source", "evaluation", "problem_set", "pricing", "judge", "context", "evidence_mode"}
    if not submission:
        required.add("request_id")
    if not isinstance(request, dict) or set(request) != required:
        raise APIError(400, "Malformed evaluation request.")
    if not submission:
        identity(request["request_id"])
    if request["protocol"] != PROTOCOL or request["evidence_mode"] != evidence_mode:
        raise APIError(400, "Evaluation evidence mode differs from this service.")
    if request["problem_set"] != problem_set:
        raise APIError(400, "Problem or pricing policy differs from the service pin.")
    if pricing_validator is not None:
        pricing_validator(request)
    elif request["pricing"] != pricing_schedule():
        raise APIError(400, "Pricing policy differs from the service pin.")
    validate_evaluation_config(request["evaluation"], pricing=request["pricing"])
    judge_input(json.dumps(request["judge"]))
    if not isinstance(request["context"], dict):
        raise APIError(400, "Missing request context.")
    source = request["source"]
    if not isinstance(source, dict) or set(source) != {"digest", "archive_base64"}:
        raise APIError(400, "Malformed source envelope.")
    try:
        archive = base64.b64decode(source["archive_base64"], validate=True)
    except (ValueError, TypeError):
        raise APIError(400, "Malformed source archive.") from None
    if len(archive) > MAX_SOURCE_BYTES:
        raise APIError(413, "Source exceeds the submission size limit.")
    snapshot, files = open_bundle(archive)
    if snapshot["kind"] != "harness" or snapshot["version"] != source["digest"]:
        raise APIError(400, "Source digest does not match the submitted harness.")
    execution = snapshot["document"].get("execution")
    validate_execution(execution)
    if execution["dockerfile"] not in files or SOURCE_EXCLUDES.intersection(files):
        raise APIError(400, "Missing Dockerfile or excluded runtime files in source.")
    return archive


class JobStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        self.path = self.root / "jobs.sqlite"
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, request_id TEXT NOT NULL,
                    request_digest TEXT NOT NULL, request TEXT NOT NULL,
                    status TEXT NOT NULL, result TEXT, created_at TEXT NOT NULL,
                    UNIQUE(owner, request_id)
                );
                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
                    status TEXT NOT NULL, at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS submissions (
                    repository TEXT NOT NULL, source_commit TEXT NOT NULL,
                    owner TEXT NOT NULL, evaluation_id TEXT NOT NULL,
                    PRIMARY KEY(repository, source_commit)
                );
                CREATE TABLE IF NOT EXISTS publications (
                    evaluation_id TEXT NOT NULL, repository TEXT NOT NULL,
                    source_commit TEXT NOT NULL, run_id TEXT NOT NULL,
                    run_attempt TEXT NOT NULL,
                    PRIMARY KEY(evaluation_id, repository, source_commit, run_id, run_attempt)
                );
            """)
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, owner, request, limits=None):
        encoded, hashed = canonical(request).decode(), digest(request)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute("SELECT * FROM jobs WHERE owner=? AND request_id=?",
                                  (owner, request["request_id"])).fetchone()
            if previous:
                if previous["request_digest"] != hashed:
                    raise APIError(409, "Operation key already belongs to another request.")
                return previous["id"]
            if limits:
                active = "status IN ('queued','building','running','verifying')"
                own = db.execute(f"SELECT count(*) FROM jobs WHERE owner=? AND {active}", (owner,)).fetchone()[0]
                total = db.execute(f"SELECT count(*) FROM jobs WHERE {active}").fetchone()[0]
                daily = db.execute("SELECT count(*) FROM jobs WHERE owner=? AND "
                                   "julianday(created_at) >= julianday('now', '-1 day')", (owner,)).fetchone()[0]
                if (own >= limits["max_active_per_owner"] or total >= limits["max_active_total"]
                        or daily >= limits["max_daily_per_owner"]):
                    raise APIError(429, "Evaluation quota reached; retry after active runs or the daily window.")
            evaluation_id = str(uuid.uuid4())
            db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,'queued',NULL,?)",
                       (evaluation_id, owner, request["request_id"], hashed, encoded, now()))
            db.execute("INSERT INTO events(job_id,status,at) VALUES (?,'queued',?)", (evaluation_id, now()))
            return evaluation_id

    def get(self, evaluation_id):
        identity(evaluation_id)
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (evaluation_id,)).fetchone()
        if row is None:
            raise APIError(404, "Evaluation not found.")
        return {**dict(row), "request": json.loads(row["request"]),
                "result": json.loads(row["result"]) if row["result"] else None}

    def view(self, evaluation_id):
        job = self.get(evaluation_id)
        return job["result"] or {**bindings(job["request"], evaluation_id),
                                 "status": job["status"], "trace_available": False}

    def own(self, evaluation_id, principal):
        job = self.get(evaluation_id)
        if principal["kind"] != "yukon-solver" or job["owner"] != principal["owner"]:
            raise APIError(404, "Evaluation not found.")
        return job

    def claim(self):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT id FROM jobs WHERE status='queued' ORDER BY created_at,id LIMIT 1").fetchone()
            if row is None:
                return None
            db.execute("UPDATE jobs SET status='building' WHERE id=?", (row["id"],))
            db.execute("INSERT INTO events(job_id,status,at) VALUES (?,'building',?)", (row["id"], now()))
        return self.get(row["id"])

    def transition(self, evaluation_id, status, result=None):
        allowed = {"building": {"running", "failed"}, "running": {"verifying", "failed"},
                   "verifying": {"completed", "failed"}}
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status FROM jobs WHERE id=?", (evaluation_id,)).fetchone()
            if row is None or status not in allowed.get(row["status"], set()):
                raise CatalystError("Invalid job state transition.")
            if status in {"completed", "failed"} and (not result or result["status"] != status):
                raise CatalystError("Terminal jobs require a durable result.")
            db.execute("UPDATE jobs SET status=?,result=? WHERE id=?",
                       (status, canonical(result).decode() if result else None, evaluation_id))
            db.execute("INSERT INTO events(job_id,status,at) VALUES (?,?,?)", (evaluation_id, status, now()))

    def recover_interrupted(self):
        # Called only under the exclusive worker lock. Never replay started work.
        with self.connect() as db:
            ids = [r["id"] for r in db.execute("SELECT id FROM jobs WHERE status IN ('building','running','verifying')")]
        for evaluation_id in ids:
            job = self.get(evaluation_id)
            self.transition(evaluation_id, "failed", {
                **bindings(job["request"], evaluation_id), "status": "failed",
                "reason": "Worker interrupted; this attempt was not restarted.",
                "trace_available": self.trace_path(evaluation_id).is_file(),
            })

    def trace_path(self, evaluation_id):
        return self.root / "artifacts" / identity(evaluation_id) / "traces.zip"

    def register_submission(self, evaluation_id, owner, repository, source_commit):
        """Trusted local fixture setup; intentionally not an HTTP write endpoint."""
        if self.get(evaluation_id)["owner"] != owner:
            raise APIError(403, "Submission owner differs from evaluation owner.")
        with self.connect() as db:
            old = db.execute("SELECT * FROM submissions WHERE repository=? AND source_commit=?",
                             (repository, source_commit)).fetchone()
            if old and (old["owner"] != owner or old["evaluation_id"] != evaluation_id):
                raise APIError(409, "Submission binding is immutable.")
            db.execute("INSERT OR IGNORE INTO submissions VALUES (?,?,?,?)",
                       (repository, source_commit, owner, evaluation_id))

    def publish(self, evaluation_id, principal, request, auth):
        auth.workflow_context(principal, request["context"])
        context = request["context"]
        job = self.get(evaluation_id)
        with self.connect() as db:
            binding = db.execute("SELECT * FROM submissions WHERE repository=? AND source_commit=?",
                                 (context["repository"], context["commit"])).fetchone()
            if (not binding or binding["owner"] != job["owner"]
                    or binding["evaluation_id"] != evaluation_id):
                raise APIError(403, "Workflow has no queued submission bound to this evaluation.")
            expected = {k: v for k, v in job["request"].items() if k not in {"request_id", "context", "judge"}}
            actual = {k: v for k, v in request.items() if k not in {"context", "judge"}}
            if expected != actual or request["judge"]["policies"] != job["request"]["judge"]["policies"]:
                raise APIError(409, "Submitted source or evaluation policy does not match the stored result.")
            if job["status"] != "completed":
                raise APIError(409, "Evaluation has no completed judgment.")
            db.execute("INSERT OR IGNORE INTO publications VALUES (?,?,?,?,?)",
                       (evaluation_id, context["repository"], context["commit"],
                        context["run_id"], context["run_attempt"]))
        return job["result"]


def handler_for(store, auth, problem_set, evidence_mode="local-test", credentials=None):
    from .pricing import PricingQuotes
    quotes = PricingQuotes(store)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Never log bearer tokens, source or request bodies.

        def send(self, status, value, mime="application/json"):
            body = value if isinstance(value, bytes) else canonical(value)
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if mime.startswith("text/html"):
                self.send_header("Content-Security-Policy",
                                 "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def artifact(self, evaluation_id, kind, *, public=False, content=False):
            from .artifacts import download
            item, signed, path = download(store, evaluation_id, kind, public=public)
            scope = "/public" if public else ""
            if not content:
                return self.send(200, {
                    **{k: v for k, v in item.items() if k != "storage"},
                    "url": signed or f"{scope}/evaluations/{evaluation_id}/artifacts/{kind}/content",
                })
            if signed:
                # Public permalink browsers can follow this; API credentials never
                # go to S3. CLI uses the descriptor URL with no Authorization header.
                self.send_response(303)
                self.send_header("Location", signed)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Length", str(item["bytes"]))
            self.send_header("Content-Disposition", f'attachment; filename="{kind}.zip"')
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            with path.open("rb") as stream:
                import shutil
                shutil.copyfileobj(stream, self.wfile)

        def dispatch(self):
            try:
                parts = self.path.strip("/").split("/")
                if self.command == "GET" and len(parts) == 3 and parts[:2] == ["public", "evaluations"]:
                    from .artifacts import public_page
                    return self.send(200, public_page(store, parts[2]), "text/html; charset=utf-8")
                if self.command == "GET" and len(parts) >= 4 and parts[:2] == ["public", "evaluations"]:
                    from .artifacts import manifest
                    if parts[3:] == ["artifacts"]:
                        return self.send(200, manifest(store, parts[2], public=True))
                    if len(parts) in {5, 6} and parts[3] == "artifacts" and (
                            len(parts) == 5 or parts[5] == "content"):
                        return self.artifact(parts[2], parts[4], public=True, content=len(parts) == 6)
                    raise APIError(404, "Not found.")
                login = self.command == "POST" and parts == ["auth", "yukon"]
                binding = self.command == "POST" and parts == ["verifications", "yukon-bind"]
                if login or binding:
                    from .hosted import ServiceIdentity
                    if not isinstance(auth, ServiceIdentity) or not auth.yukon:
                        raise APIError(404, "Yukon login is not enabled.")
                else:
                    principal = auth.authenticate(self.headers.get("Authorization"))
                if self.command == "POST":
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= (1024 if login else 128 * 1024 if binding else BODY_LIMIT):
                        raise APIError(413, "Invalid request size.")
                    if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                        raise APIError(415, "JSON required.")
                    request = json.loads(self.rfile.read(length))
                    if login:
                        from .yukon_auth import PROTOCOL as SESSION_PROTOCOL
                        if request != {"protocol": SESSION_PROTOCOL}:
                            raise APIError(400, "Invalid Yukon login request.")
                        return self.send(200, auth.yukon.exchange(self.headers.get("Authorization")))
                    if binding:
                        from .yukon_binding import bind_execution
                        return self.send(200, bind_execution(
                            store, auth, self.headers.get("Authorization"), request))
                    if parts == ["verifications", "retrieve"]:
                        from .hosted import retrieve_receipt
                        return self.send(200, retrieve_receipt(store, auth, principal, request))
                    if parts == ["yukon", "v1", "retrieve"]:
                        from .hosted import retrieve_verification
                        return self.send(200, retrieve_verification(store, principal, request))
                    if parts == ["pricing", "quote"]:
                        if (evidence_mode != "remote" or principal["kind"] != "yukon-solver"
                                or not isinstance(request, dict) or set(request) != {"models"}):
                            raise APIError(403, "Pricing quotes require an authenticated solver.")
                        return self.send(200, {"pricing": quotes.issue(request["models"])})
                    if len(parts) == 3 and parts[0] == "evaluations" and parts[2] == "yukon":
                        from .hosted import retrieve_for_yukon
                        return self.send(200, retrieve_for_yukon(store, parts[1], principal, request))
                    if parts == ["evaluations"]:
                        validate_request(request, problem_set, evidence_mode=evidence_mode,
                            pricing_validator=lambda value: quotes.validate(value, owner=principal.get("owner")))
                        auth.authorize_run(principal, request)
                        from .model_access import TOKEN_HEADER, temporary_access
                        token = self.headers.get(TOKEN_HEADER)
                        if temporary_access(request["evaluation"]):
                            if credentials is None or evidence_mode != "remote":
                                raise APIError(403, "Temporary model access is not enabled.")
                            try:
                                evaluation_id = credentials.enqueue(
                                    principal["owner"], request, auth.creation_limits(), token)
                            finally:
                                token = None
                                del self.headers[TOKEN_HEADER]
                        else:
                            if token is not None:
                                raise APIError(400, "This evaluation does not request temporary model access.")
                            evaluation_id = store.create(principal["owner"], request, auth.creation_limits())
                        return self.send(202, {"request_id": request["request_id"], "evaluation_id": evaluation_id})
                    if len(parts) == 3 and parts[0] == "evaluations" and parts[2] == "sharing":
                        store.own(parts[1], principal)
                        from .artifacts import publish
                        return self.send(200, publish(store, parts[1], request))
                    if len(parts) == 3 and parts[0] == "evaluations" and parts[2] == "submissions":
                        validate_request(request, problem_set, submission=True, evidence_mode=evidence_mode,
                            pricing_validator=lambda value: quotes.validate(value, historical=True))
                        return self.send(200, store.publish(parts[1], principal, request, auth))
                elif self.command == "GET" and 2 <= len(parts) <= 5 and parts[0] == "evaluations":
                    store.own(parts[1], principal)
                    if len(parts) == 2:
                        return self.send(200, store.view(parts[1]))
                    if parts[2] == "traces":
                        path = store.trace_path(parts[1])
                        if not path.is_file():
                            raise APIError(404, "Traces are not available yet.")
                        return self.send(200, path.read_bytes(), "application/zip")
                    if parts[2:] == ["sharing"]:
                        from .artifacts import sharing
                        return self.send(200, sharing(store, parts[1]))
                    if parts[2:] == ["artifacts"]:
                        from .artifacts import manifest
                        return self.send(200, manifest(store, parts[1]))
                    if len(parts) in {4, 5} and parts[2] == "artifacts" and (
                            len(parts) == 4 or parts[4] == "content"):
                        return self.artifact(parts[1], parts[3], content=len(parts) == 5)
                raise APIError(404, "Not found.")
            except APIError as error:
                if self.command == "POST" and parts == ["verifications", "retrieve"] and error.status in {401, 403}:
                    # These are service-authored rejection reasons. Do not log
                    # request headers, token claims, receipts or request bodies.
                    logging.getLogger(__name__).warning(
                        "Receipt retrieval rejected (HTTP %d): %s", error.status, str(error))
                self.send(error.status, {"error": str(error)})
            except (CatalystError, ValueError, KeyError, TypeError):
                self.send(400, {"error": "Invalid evaluation request."})

        do_GET = dispatch
        do_POST = dispatch

    return Handler


def serve(state, auth_file, problem_set_file, port, worker_config=None):
    from .service import WorkerSupervisor, termination_as_interrupt
    worker_config = worker_config or auth_file.parent / "worker.json"
    from .hosted import ServiceIdentity
    auth_config = read_json(auth_file)
    auth = ServiceIdentity(auth_config) if auth_config.get("mode") == "service" else LocalIdentity(auth_config)
    problem_set = read_json(problem_set_file)
    config = read_json(worker_config)
    mode = config.get("mode")
    if (mode not in {"local-test", "local-ecdsa", "remote"} or not config.get("problem_set")
            or read_json(Path(config["problem_set"])) != problem_set):
        raise CatalystError("Worker configuration must match the API's local problem set.")
    permitted_access = {"disabled", "temporary"} if mode == "remote" else {"disabled"}
    if mode in {"local-ecdsa", "remote"} and (
            problem_set != initial_problems() or config.get("model_access") not in permitted_access):
        raise CatalystError("ECDSA requires the pinned official problem and a supported model-access mode.")
    if (mode == "remote") != isinstance(auth, ServiceIdentity):
        raise CatalystError("Remote execution requires service identities; local fixtures cannot authorize it.")
    store = JobStore(state)
    from .model_access import CredentialInbox
    credentials = CredentialInbox(store) if config.get("model_access") == "temporary" else None

    class SupervisedServer(ThreadingHTTPServer):
        def service_actions(self):
            supervisor.check()
            if credentials:
                credentials.sweep()

    with termination_as_interrupt():
        with SupervisedServer(("127.0.0.1", port), handler_for(store, auth, problem_set, mode, credentials)) as server:
            supervisor = WorkerSupervisor(store, worker_config, credentials)
            try:
                supervisor.wait_ready()
                print(f"Catalyst verification API: http://127.0.0.1:{server.server_port}", flush=True)
                print(f"Problem: {problem_set[0]['id'] if problem_set else 'none'}; evidence: {mode}", flush=True)
                print(f"Managed worker: PID {supervisor.process.pid}; log: {supervisor.log_path}", flush=True)
                server.serve_forever(poll_interval=.2)
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
                supervisor.close()
