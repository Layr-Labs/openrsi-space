"""Persistent worker for the local circuit fixture and real pinned ECDSA task."""
from __future__ import annotations

import base64
from contextlib import contextmanager
from decimal import Decimal
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import tomllib
import zipfile

from .common import CatalystError, digest_files, extract_bundle, read_json, write_json
from .dungeness import prepare
from .evaluator import JobStore, bindings
from .executable import build
from .local_run import FIXTURE_URL, MockProvider
from .tiers import TIERS, credits, pricing_digest
from .remote import judgment
from .problems import get_problem, initial_problems

_SUPERVISOR_FD = None


def notify_supervisor(event, **fields):
    if _SUPERVISOR_FD is not None:
        try:
            os.write(_SUPERVISOR_FD, (json.dumps({"event": event, **fields}) + "\n").encode())
        except BrokenPipeError:
            raise KeyboardInterrupt from None


@contextmanager
def worker_lock(store):
    with (store.root / "worker.lock").open("a") as file:
        try:
            fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise CatalystError("A worker already owns this job store.") from None
        try:
            yield
        finally:
            fcntl.flock(file, fcntl.LOCK_UN)


def run_command(command, cwd, environment, output, timeout):
    """Bound the process tree, giving Dungeness time to tear down its containers."""
    with output.open("w") as log:
        process = subprocess.Popen(command, cwd=cwd, env=environment, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            notify_supervisor("started", pid=process.pid)
            code = process.wait(timeout=timeout)
        except BaseException:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGINT)
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
            raise
        finally:
            notify_supervisor("stopped", pid=process.pid)
    if code:
        raise CatalystError(f"Worker command exited {code}; see private {output.name}.")


def capture_file(source, destination):
    if source.is_symlink() or not source.is_file():
        raise CatalystError("Candidate artifact must be a regular file.")
    with source.open("rb") as file:
        data = file.read(8 * 1024 * 1024 + 1)
    if len(data) > 8 * 1024 * 1024:
        raise CatalystError("Candidate artifact is too large.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    destination.chmod(0o444)
    return digest_files({"candidate.json": data})


def candidate_files(source, relative):
    """Read bounded regular files from a stopped harness's retained candidate."""
    if source.is_symlink() or not source.exists():
        raise CatalystError("Candidate must exist and cannot be a symlink.")
    paths = sorted(source.rglob("*")) if source.is_dir() else [source]
    files, size = {}, 0
    for path in paths:
        if path.is_symlink():
            raise CatalystError("Candidate symlinks are not allowed.")
        if path.is_dir():
            continue
        if not path.is_file():
            raise CatalystError("Candidate contains a non-regular file.")
        if len(files) >= 2000:
            raise CatalystError("Candidate contains too many files.")
        with path.open("rb") as file:
            data = file.read(8 * 1024 * 1024 - size + 1)
        size += len(data)
        if size > 8 * 1024 * 1024:
            raise CatalystError("Candidate exceeds 8 MiB.")
        key = relative + "/" + path.relative_to(source).as_posix() if source.is_dir() else relative
        files[key] = data
    if not files:
        raise CatalystError("Candidate has no files.")
    return files


def capture_candidate(source, root, relative):
    files = candidate_files(source, relative)
    for name, data in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(0o444)
    return digest_files(files)


def collect_usage(run_dir, evaluation):
    events_file = run_dir / "usage/events.jsonl"
    if not events_file.is_file():
        raise CatalystError("Dungeness did not retain its trusted usage ledger.")
    ledger, seen, total = [], set(), Decimal(0)
    for line in events_file.read_text().splitlines():
        event = json.loads(line)
        if event.get("source") != "gateway" or event.get("kind") != "model.accounting":
            continue
        data = event["data"]
        if (data.get("accounting_method") != "gateway"
                or data.get("provider") != evaluation["model"]["provider"]
                or data.get("model") != evaluation["model"]["name"]):
            raise CatalystError("Missing usage or unexpected model in Dungeness accounting.")
        request_id = event.get("request_id")
        if not isinstance(request_id, str) or not request_id or request_id in seen:
            raise CatalystError("Duplicate or unidentified model receipt.")
        seen.add(request_id)
        # Dungeness includes reasoning in output_tokens and cache subsets in input_tokens.
        tokens = {"input_tokens": data.get("input_tokens"), "output_tokens": data.get("output_tokens"),
                  "cached_read_tokens": data.get("cached_input_tokens", 0),
                  "cache_write_tokens": data.get("cache_write_input_tokens", 0)}
        total += credits(tokens, evaluation["model"])
        ledger.append({"sequence": len(ledger) + 1, "request_id": request_id,
                       "settled": True, "tokens": tokens})
    record = read_json(run_dir / "record.json")
    recorded = record["data"]["usage"].get("normalized_usd")
    if recorded is None or Decimal(str(recorded)) != total:
        raise CatalystError("Dungeness terminal usage disagrees with the pinned pricing ledger.")
    return ledger, total


def verify_ecdsa(runtime, run_dir, run_id, candidate, relative, environment, artifacts, timeout):
    """Run the unchanged pinned verifier; return root-created output to its host owner."""
    task = run_dir / "debug/harbor-task"
    resources = tomllib.loads((task / "task.toml").read_text())
    memory = resources["verifier"]["environment"]["memory_mb"]
    if type(memory) is not int or memory <= 0:
        raise CatalystError("Retained verifier memory limit is invalid.")
    output = run_dir / "verify-out"
    output.mkdir()  # Every evaluation gets a fresh output directory.
    image = "catalyst-verify-" + run_id
    run_command(["docker", "build", "-t", image, str(task / "tests")],
                runtime, environment, artifacts / "verifier-build.log", timeout)
    # The ECDSA verifier intentionally makes /logs/verifier root-only. On Linux
    # bind mounts this also changes host ownership. Restore only this run's
    # output after grading, retaining its permissions and verifier exit code.
    command = '/tests/test.sh; result=$?; chown -R "$1:$2" /logs/verifier || exit 1; exit "$result"'
    run_command(["docker", "run", "--rm", "--network", "none", "--memory", f"{memory}m",
                 "-v", f"{candidate}:/workspace/repo/{relative}:ro",
                 "-v", f"{output}:/logs/verifier", "--entrypoint", "/bin/sh", image,
                 "-c", command, "--", str(os.getuid()), str(os.getgid())],
                runtime, environment, artifacts / "verification.log", timeout)


class DungenessLocalBackend:
    def __init__(self, config):
        if config.get("mode") not in {"local-test", "local-ecdsa", "remote"}:
            raise CatalystError("Only local fixture and local ECDSA workers are enabled.")
        if config["mode"] in {"local-ecdsa", "remote"} and config.get("model_access") != "disabled":
            raise CatalystError("The real ECDSA baseline requires disabled model access.")
        self.config = config

    def evaluate(self, job, artifacts, transition):
        request = job["request"]
        real = self.config["mode"] in {"local-ecdsa", "remote"}
        if (request["evidence_mode"] != self.config["mode"]
                or request["problem_set"] != read_json(Path(self.config["problem_set"]))):
            raise CatalystError("Worker problem or evidence mode differs from the request.")
        if real:
            if request["problem_set"] != initial_problems():
                raise CatalystError("Real ECDSA requires the official problem pin.")
            package = read_json(Path(self.config["problem"]) / "problem.json")
            if package["execution"] != get_problem("ecdsa.fail")["dungeness"]:
                raise CatalystError("ECDSA task/checkpoint binding differs from the official pin.")
        elif request["problem_set"][0]["id"] != "local-circuit-fixture":
            raise CatalystError("Fixture worker requires the local circuit problem.")
        relative = request["problem_set"][0]["candidate_paths"][0]
        evaluation = request["evaluation"]
        if evaluation["model"] != {"provider": "openai", "name": "gpt-5.6-sol"}:
            raise CatalystError("The local mock provider supports only the pinned fixture model.")
        work_state = Path(self.config["state"])
        source = artifacts / "source"
        extract_bundle(base64.b64decode(request["source"]["archive_base64"]), source)
        built = build(work_state, source, timeout=300)
        build_identity = {"id": built["id"], "image_digest": built["image_id"],
                          "image_identity_kind": "docker-image-id", "evidence": self.config["mode"]}
        write_json(artifacts / "build.json", build_identity)
        with MockProvider(evaluation, allow_model_calls=not real) as provider:
            env_file = artifacts / "mock-provider.env"
            env_file.write_text(
                f"TESTBED_OPENAI_API_KEY={provider.key}\n"
                f"OPENAI_UPSTREAM_BASE_URL=http://host.docker.internal:{provider.server.server_port}/v1\n")
            env_file.chmod(0o600)
            try:
                metadata = prepare(work_state, Path(self.config["problem"]), source,
                                   evaluation["max_model_credits"], evaluation["limits"]["max_model_tokens"],
                                   env_file=str(env_file), build_id=built["id"], model=evaluation["model"]["name"])
                write_json(artifacts / "runtime.json", metadata)
                runtime = Path(metadata["runtime"])
                run_dir = Path(metadata["record_path"]).parent
                # Never inherit provider credentials, tokens or a real provider override.
                environment = {key: os.environ[key] for key in
                               ("PATH", "HOME", "TMPDIR", "USER", "LOGNAME", "DOCKER_HOST", "DOCKER_CONTEXT")
                               if key in os.environ}
                environment["UV_CACHE_DIR"] = str(work_state / "uv-cache")
                if not real:
                    environment.update({
                        "GIT_CONFIG_COUNT": "1",
                        "GIT_CONFIG_KEY_0": f"url.file://{self.config['repository']}.insteadOf",
                        "GIT_CONFIG_VALUE_0": FIXTURE_URL,
                    })
                transition("running")
                run_command(
                    [sys.executable, *metadata["command"], "--keep-render", "--keep-images",
                     "--agent-timeout-sec", str(evaluation["limits"]["max_seconds"])],
                    runtime, environment, artifacts / "execution.log",
                    timeout=self.config.get("execution_timeout_sec", evaluation["limits"]["max_seconds"] + 600),
                )
                if real and provider.attempts:
                    raise CatalystError("The harness requested a model, but this ECDSA service disables model access.")
                ledger, total = collect_usage(run_dir, evaluation)
                if total != provider.total or len(ledger) != len(provider.receipts):
                    raise CatalystError("Gateway receipts disagree with the mock provider's independently metered usage.")
                write_json(artifacts / "usage.json", ledger)
                # The harness has stopped; retained artifacts cannot change during this capture.
                candidates = list(run_dir.glob("harbor/*/*/artifacts/workspace/repo/" + relative))
                if len(candidates) != 1:
                    raise CatalystError("Expected exactly one retained candidate artifact.")
                candidate_file = artifacts / "candidate" / relative
                candidate_digest = capture_candidate(candidates[0], artifacts / "candidate", relative)
                capture_seq = len(ledger) + 1
                transition("verifying")
                # Re-run the exact trusted verifier against the frozen candidate, with no network.
                verification_timeout = self.config.get("verification_timeout_sec", 180)
                if real:
                    verify_ecdsa(runtime, run_dir, metadata["id"], candidate_file, relative,
                                 environment, artifacts, verification_timeout)
                else:
                    run_command([sys.executable, str(runtime / "dungeness"), "verify",
                                 metadata["id"], str(candidate_file), "--memory", "1g"],
                                runtime, environment, artifacts / "verification.log",
                                timeout=verification_timeout)
                verified = read_json(run_dir / "verify-out/score.json")
                if candidate_digest != digest_files(candidate_files(candidate_file, relative)):
                    raise CatalystError("Captured candidate changed during verification.")
                write_json(artifacts / "verification.json", verified)
                points = []
                if (verified.get("status") == "ok"
                        and (verified.get("metric") == "ecdsafail_score" if real else verified.get("valid") is True)):
                    points.append({
                        "candidate_digest": candidate_digest, "verified_candidate_digest": candidate_digest,
                        "captured_sequence": capture_seq, "verified": True, "settled": True,
                        "normalized_model_usd": float(total), "avg_toffoli": verified["avg_toffoli"],
                        "peak_qubits": verified["peak_qubits"], "performance": verified["score"],
                    })
                # Only terminal windows within the actual allowance are sealed.
                # Earlier windows crossed during execution remain explicitly unmeasured.
                checkpoints = []
                seq = capture_seq
                for budget in TIERS:
                    if total <= budget <= evaluation["max_model_credits"]:
                        seq += 1
                        checkpoints.append({"budget_tier": budget, "sequence": seq, "settled": True})
                observation = {
                    "problem_id": request["problem_set"][0]["id"],
                    "problem_commit": request["problem_set"][0]["repository"]["commit"],
                    "pricing_digest": pricing_digest(), "normalized_model_usd": float(total),
                    "end_sequence": seq + 1, "usage": ledger, "curve": points, "checkpoints": checkpoints,
                }
                label = "Pinned ecdsa.fail candidate" if real else "Local circuit fixture (not ECDSA)"
                return {"build": build_identity, "observations": [observation], "valid": bool(points),
                        "model_access": "disabled" if real else "mock",
                        "reason": f"{label} independently verified."
                                  if points else f"{label} failed independent verification."}
            finally:
                env_file.unlink(missing_ok=True)
                # The only credential used here is a short-lived mock key.
                for log in artifacts.glob("*.log"):
                    log.write_text(log.read_text(errors="replace").replace(provider.key, "[REDACTED]"))


def archive_traces(folder):
    """Allowlisted artifacts only; no auth files, env files, or build context."""
    names = ("build.json", "runtime.json", "execution.log", "verifier-build.log", "verification.log", "failure.json",
             "usage.json", "verification.json")
    temporary = folder / "traces.zip.tmp"
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            path = folder / name
            if path.is_file() and not path.is_symlink():
                archive.write(path, name)
        for path in sorted((folder / "candidate").rglob("*")):
            if path.is_file() and not path.is_symlink():
                archive.write(path, path.relative_to(folder).as_posix())
    temporary.chmod(0o600)
    temporary.replace(folder / "traces.zip")


def run_one(store, backend):
    job = store.claim()
    if job is None:
        return None
    evaluation_id = job["id"]
    folder = store.trace_path(evaluation_id).parent
    folder.mkdir(parents=True, mode=0o700)
    result = bindings(job["request"], evaluation_id)
    try:
        outcome = backend.evaluate(job, folder, lambda status: store.transition(evaluation_id, status))
        result.update(outcome, status="completed", trace_available=True)
        judgment(result, job["request"])  # Fail closed before persisting a public judgment.
        archive_traces(folder)
        store.transition(evaluation_id, "completed", result)
    except Exception as error:
        # Error type and fixed failure text are public; tool output remains private.
        write_json(folder / "failure.json", {"type": type(error).__name__, "message": str(error)})
        archive_traces(folder)
        result.update(status="failed", reason="Worker failed; inspect the private trace archive.",
                      trace_available=True)
        store.transition(evaluation_id, "failed", result)
    return evaluation_id


def work(state, config_path, *, once=False, supervisor_fd=None):
    global _SUPERVISOR_FD
    from .service import termination_as_interrupt
    store = JobStore(state)
    backend = DungenessLocalBackend(read_json(config_path))
    _SUPERVISOR_FD = supervisor_fd
    try:
        with termination_as_interrupt(), worker_lock(store):
            store.recover_interrupted()
            try:
                notify_supervisor("ready")
                while True:
                    evaluation_id = run_one(store, backend)
                    if evaluation_id:
                        print(f"{evaluation_id}: {store.get(evaluation_id)['status']}", flush=True)
                    if once:
                        return
                    if not evaluation_id:
                        time.sleep(.25)
            except KeyboardInterrupt:
                store.recover_interrupted()
    finally:
        _SUPERVISOR_FD = None
        if supervisor_fd is not None:
            os.close(supervisor_fd)
