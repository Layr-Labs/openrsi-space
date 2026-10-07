"""Set up an explicit local-only integration workspace and a mock provider."""
from __future__ import annotations

from decimal import Decimal
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import shutil
import threading

from .common import CatalystError, write_json
from .dungeness import configure, git, native_problem
from .problems import get_problem, initial_problems
from .tiers import credits

FIXTURE = Path(__file__).parent / "local_fixture"
MODEL = {"provider": "openai", "name": "gpt-5.6-sol"}
FIXTURE_URL = "https://catalyst.invalid/local-circuit.git"
WORKFLOW_CONTEXT = {"kind": "github-actions", "repository": "local/catalyst",
                    "commit": "c" * 40, "run_id": "1", "run_attempt": "1"}


def initialize(root: Path, dungeness: Path, base_image="python:3.12-slim-bookworm"):
    root = root.resolve()
    if root.exists():
        raise CatalystError("Choose a new local integration directory; existing work is preserved.")
    if not base_image or any(c.isspace() for c in base_image):
        raise CatalystError("Invalid fixture base image.")
    root.mkdir(parents=True, mode=0o700)
    worker_state = root / "worker"
    configure(worker_state, dungeness)
    repository = root / "fixture-repository"
    repository.mkdir()
    shutil.copyfile(FIXTURE / "candidate.json", repository / "candidate.json")
    git(repository, "init", "--quiet")
    git(repository, "add", "candidate.json")
    # This is a private generated test repository, never the user's checkout.
    git(repository, "-c", "user.name=Local fixture", "-c", "user.email=fixture@localhost",
        "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "Local circuit fixture")
    revision = git(repository, "rev-parse", "HEAD")
    problem = {"id": "local-circuit-fixture", "title": "Local circuit integration fixture (not ECDSA)",
               "repository": {"url": FIXTURE_URL, "commit": revision},
               "candidate_paths": ["candidate.json"],
               "metric": {"name": "ecdsafail_score", "direction": "minimize"}}
    write_json(root / "problem-set.json", [problem])
    package = root / "problem"
    write_json(package / "problem.json", {
        "schema_version": 1, "kind": "problem", "id": problem["id"], "title": problem["title"],
        "metric": problem["metric"], "execution": {
            "repository": problem["repository"], "candidate_paths": ["candidate.json"],
            "interface": "catalyst-file-v1", "verifier_include": ["candidate.json"],
            "timeout_sec": 60,
        },
    })
    (package / "instructions.md").write_text(
        "Return a JSON circuit with gates [control_a, control_b, target] on 3 bits "
        "implementing Toffoli(0,1,2). Minimize gate count times qubits. This is a local test.\n")
    verifier = package / "verifier"
    verifier.mkdir()
    shutil.copyfile(FIXTURE / "grade.py", verifier / "grade.py")
    (verifier / "test.sh").write_text("#!/bin/sh\nset -eu\nexec python3 /tests/grade.py\n")
    (verifier / "Dockerfile").write_text(
        f"FROM {base_image}\nUSER root\nCOPY grade.py test.sh /tests/\n"
        "RUN chmod 0555 /tests/test.sh && mkdir -p /logs/verifier\n"
        "ENV CANDIDATE_PATH=/workspace/repo/candidate.json\n"
        "CMD [\"/tests/test.sh\"]\n")
    solver = root / "solver"
    submission = solver / "submission"
    write_json(submission / "harness.json", {
        "schema_version": 1, "kind": "harness", "id": "local-fixture", "title": "Local mock-provider harness",
        "execution": {"interface": "catalyst-exec-v1", "dockerfile": "Dockerfile",
                      "entrypoint": ["python3", "/opt/harness/agent.py"]},
    })
    shutil.copyfile(FIXTURE / "agent.py", submission / "agent.py")
    (submission / "Dockerfile").write_text(
        f"FROM {base_image}\nCOPY agent.py /opt/harness/agent.py\nWORKDIR /workspace/repo\n")
    (submission / "instructions.md").write_text("Use the supplied model endpoint and write candidate.json.\n")
    evaluation = {"schema_version": 3, "llm_access": {"grant_id": "grant_local_fixture"},
                  "model": MODEL, "max_model_credits": 20,
                  "limits": {"max_model_tokens": 100000, "max_seconds": 60}}
    write_json(submission / "evaluation.json", evaluation)
    write_local_auth(root, evaluation)
    write_json(root / "worker.json", {"mode": "local-test", "state": str(worker_state),
                                     "problem": str(package), "repository": str(repository),
                                     "problem_set": str(root / "problem-set.json")})
    return {"root": str(root), "solver": str(solver), "evidence": "local-test"}


def write_local_auth(root, evaluation):
    solver_token, workflow_token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    auth = {"mode": "local-test", "tokens": {
        hashlib.sha256(solver_token.encode()).hexdigest(): {"kind": "yukon-solver", "owner": "local-solver"},
        hashlib.sha256(workflow_token.encode()).hexdigest(): {"kind": "github-actions", "context": WORKFLOW_CONTEXT},
    }, "grants": {evaluation["llm_access"]["grant_id"]: {"owner": "local-solver", "model": MODEL,
                                         "max_model_credits": 200, "limits": evaluation["limits"]}}}
    write_json(root / "auth.json", auth)
    write_json(root / "client-tokens.json", {"solver": solver_token, "workflow": workflow_token})
    (root / "client-tokens.json").chmod(0o600)


def initialize_ecdsa(root: Path, dungeness: Path):
    root = root.resolve()
    if root.exists():
        raise CatalystError("Choose a new ECDSA service directory; existing work is preserved.")
    root.mkdir(parents=True, mode=0o700)
    config = configure(root / "worker", dungeness)
    problem = get_problem("ecdsa.fail")
    execution, metric, instruction = native_problem(
        Path(config["dungeness"]["path"]), problem["dungeness"]["task"], problem["dungeness"]["checkpoint"])
    write_json(root / "problem-set.json", initial_problems())
    package = root / "problem"
    write_json(package / "problem.json", {
        "schema_version": 1, "kind": "problem", "id": problem["id"],
        "title": problem["title"], "metric": metric, "execution": execution,
    })
    (package / "instructions.md").write_text(instruction)
    evaluation = {"schema_version": 3, "llm_access": {"grant_id": "grant_local_ecdsa"},
                  "model": MODEL, "max_model_credits": 20,
                  "limits": {"max_model_tokens": 100000, "max_seconds": 60}}
    write_local_auth(root, evaluation)
    write_json(root / "worker.json", {
        "mode": "local-ecdsa", "model_access": "disabled", "state": str(root / "worker"),
        "problem": str(package), "problem_set": str(root / "problem-set.json"),
        "execution_timeout_sec": 3600, "verification_timeout_sec": 3600,
    })
    return {"root": str(root), "problem": problem["id"], "evidence": "local-ecdsa",
            "model_access": "disabled"}


class MockProvider:
    """Deterministic model responses with real HTTP and bounded token accounting."""

    def __init__(self, evaluation, *, allow_model_calls=True):
        self.evaluation = evaluation
        self.key = secrets.token_urlsafe(32)
        self.receipts = []
        self.lock = threading.Lock()
        self.total = Decimal(0)
        self.tokens = 0
        self.attempts = 0
        provider = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, status, document):
                payload = json.dumps(document).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_POST(self):
                if self.headers.get("Authorization") != "Bearer " + provider.key:
                    return self.reply(401, {"error": "unauthorized"})
                with provider.lock:
                    provider.attempts += 1
                if not allow_model_calls:
                    return self.reply(403, {"error": "Model calls are disabled for the ECDSA baseline service."})
                if self.path != "/v1/chat/completions":
                    return self.reply(404, {"error": "unsupported local-test operation"})
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    if not 0 < length <= 1024 * 1024:
                        raise ValueError
                    request = json.loads(self.rfile.read(length))
                    if request.get("model") != evaluation["model"]["name"]:
                        raise ValueError
                except (ValueError, TypeError):
                    return self.reply(400, {"error": "invalid model request"})
                tokens = {"input_tokens": 20000, "output_tokens": 5000,
                          "cached_read_tokens": 0, "cache_write_tokens": 0}
                cost = credits(tokens, evaluation["model"])
                with provider.lock:
                    if (provider.total + cost > Decimal(str(evaluation["max_model_credits"]))
                            or provider.tokens + 25000 > evaluation["limits"]["max_model_tokens"]):
                        return self.reply(402, {"error": "authorized budget exhausted"})
                    provider.total += cost
                    provider.tokens += 25000
                    provider.receipts.append(tokens)
                return self.reply(200, {
                    "id": "local-mock-response", "object": "chat.completion",
                    "model": evaluation["model"]["name"],
                    "choices": [{"index": 0, "message": {"role": "assistant",
                                  "content": json.dumps({"gates": [[0, 1, 2]]})}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 20000, "completion_tokens": 5000, "total_tokens": 25000},
                })

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
