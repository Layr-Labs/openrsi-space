#!/usr/bin/env python3
"""Run the actual Yukon/API/Dungeness/verifier path with a mock model provider."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import re
import time
import uuid
import zipfile

from catalyst.common import extract_bundle, read_json, snapshot_directory, write_json
from catalyst.dungeness import git
from catalyst.evaluator import JobStore
from catalyst.executable import SOURCE_EXCLUDES
from catalyst.local_run import initialize, WORKFLOW_CONTEXT
from catalyst.yukon import publish_verified

PROJECT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dungeness", required=True, type=Path)
    parser.add_argument("--yukon", required=True, type=Path)
    parser.add_argument("--base-image", default="python:3.12-slim-bookworm")
    parser.add_argument("--harness", type=Path, help="Use this harness instead of the generated fixture harness.")
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    root = PROJECT / ".catalyst/local-mvp" / f"{stamp}-{uuid.uuid4().hex[:6]}"
    print(f"Local integration workspace: {root}", flush=True)
    initialize(root, args.dungeness.resolve(), args.base_image)
    solver = root / "solver"
    if args.harness:
        # Preserve the generated starter and copy the chosen source unchanged.
        (solver / "submission").rename(root / "generated-fixture-submission")
        _, archive = snapshot_directory(args.harness.resolve(), exclude=frozenset({"verification.json"}))
        extract_bundle(archive, solver / "submission")
    submitted_source, _ = snapshot_directory(solver / "submission", exclude=SOURCE_EXCLUDES)
    manifest = read_json(PROJECT / "benchmark.json")
    manifest["benchmarkCommand"] = [sys.executable, "-m", "catalyst.cli", "yukon-run"]
    write_json(solver / "benchmark.json", manifest)
    git(solver, "init", "--quiet")
    write_json(root / "yukon-config/yukon/config.json", {"telemetry": False})
    tokens = read_json(root / "client-tokens.json")
    store = JobStore(root / "service")
    # Explicit allowlist: no real model credentials are inherited by either child.
    environment = {key: os.environ[key] for key in
                   ("PATH", "HOME", "TMPDIR", "USER", "LOGNAME", "DOCKER_HOST", "DOCKER_CONTEXT")
                   if key in os.environ}
    environment["PYTHONPATH"] = str(PROJECT / "src")
    service_log_path = root / "service.log"
    service_log = service_log_path.open("w")
    service = subprocess.Popen(
        [sys.executable, "-m", "catalyst.cli", "--state", str(root / "service"),
         "evaluator-serve", "--local-test", "--auth-file", str(root / "auth.json"),
         "--problem-set", str(root / "problem-set.json"), "--port", "0"],
        cwd=PROJECT, env=environment, stdout=service_log, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 15
        while True:
            if service.poll() is not None:
                raise RuntimeError(f"Service startup failed; see {service_log_path}")
            output = service_log_path.read_text()
            address = re.search(r"Local-test verification API: (http://127.0.0.1:\d+)", output)
            managed = re.search(r"Managed worker: PID (\d+)", output)
            if address and managed:
                base, worker_pid = address.group(1), int(managed.group(1))
                break
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Service startup timed out; see {service_log_path}")
            time.sleep(.05)
        environment.update({
            "CATALYST_EVALUATOR_URL": base, "CATALYST_LOCAL_TEST": "1",
            "CATALYST_LOCAL_PROBLEM_SET": str(root / "problem-set.json"),
            "CATALYST_API_TOKEN": tokens["solver"], "YUKON_CONFIG_DIR": str(root / "yukon-config"),
        })
        print("Submitting with the standalone Catalyst CLI…", flush=True)
        submitted = subprocess.run(
            [sys.executable, "-m", "catalyst.cli", "remote", "submit"],
            cwd=solver, env=environment, check=True, capture_output=True, text=True, timeout=60)
        submitted_id = json.loads(submitted.stdout)["evaluation_id"]
        print(f"Running the actual Yukon CLI to resume evaluation {submitted_id}…", flush=True)
        subprocess.run(["bun", str(args.yukon.resolve() / "apps/cli/src/yukon.ts"), "run"],
                       cwd=solver, env=environment, check=True, timeout=1200)
        score = read_json(solver / manifest["scorePath"])
        receipt = read_json(solver / "submission/verification.json")
        evaluation_id = receipt["evaluation_id"]
        assert evaluation_id == submitted_id
        # A separate invocation can retrieve the same result after Yukon finishes.
        waited = subprocess.run(
            [sys.executable, "-m", "catalyst.cli", "remote", "wait", evaluation_id],
            cwd=solver, env=environment, check=True, capture_output=True, text=True, timeout=60)
        assert json.loads(waited.stdout)["scores"] == score["scores"]
        job = store.get(evaluation_id)
        assert job["request"]["source"]["digest"] == submitted_source["version"]
        assert score["scores"] == [3.0, .25], score
        assert score["metrics"]["evidenceMode"] == "local-test"
        with zipfile.ZipFile(store.trace_path(evaluation_id)) as archive:
            assert archive.testzip() is None
            assert json.loads(archive.read("verification.json"))["score"] == 3
            assert not any(name.endswith(".env") for name in archive.namelist())
        # Stand in only for Yukon's external submission/identity service.
        store.register_submission(evaluation_id, "local-solver", WORKFLOW_CONTEXT["repository"],
                                  WORKFLOW_CONTEXT["commit"])
        body = {k: v for k, v in job["request"].items() if k != "request_id"}
        body["context"] = WORKFLOW_CONTEXT
        workflow_score = root / "workflow-score.json"
        print("Fetching the same result through the workflow publication client…", flush=True)
        for _ in range(2):
            published = publish_verified(workflow_score, solver / "submission/verification.json",
                                         body, base, tokens["workflow"])
            assert published["scores"] == score["scores"]
        # Reopening the database proves the result is durable across service restarts.
        restarted = JobStore(root / "service")
        assert restarted.view(evaluation_id) == job["result"]
        with restarted.connect() as db:
            states = [row["status"] for row in db.execute(
                "SELECT status FROM events WHERE job_id=? ORDER BY sequence", (evaluation_id,))]
            assert states == ["queued", "building", "running", "verifying", "completed"], states
            assert db.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1
            assert db.execute("SELECT count(*) FROM publications").fetchone()[0] == 1
        summary = {"evidence": "local-test", "evaluation_id": evaluation_id, "scores": score["scores"],
                   "jobs": 1, "model_requests": len(job["result"]["observations"][0]["usage"]),
                   "workflow_replays": 2, "states": states, "workspace": str(root)}
        summary["standalone_cli"] = "submit and wait passed; Yukon reused the same evaluation"
        summary["harness"] = submitted_source["id"]
        summary["source_digest"] = submitted_source["version"]
        write_json(root / "summary.json", summary)
        print(json.dumps(summary, indent=2), flush=True)
    finally:
        service.send_signal(signal.SIGTERM)
        try:
            if service.wait(timeout=40) != 0:
                raise RuntimeError(f"Service exited unsuccessfully; see {service_log_path}")
        except subprocess.TimeoutExpired:
            service.kill()
            service.wait()
            raise RuntimeError("Service failed to stop its worker.")
        finally:
            service_log.close()
        if "worker_pid" in locals():
            try:
                os.kill(worker_pid, 0)
            except ProcessLookupError:
                pass
            else:
                raise RuntimeError("Service left its worker running.")


if __name__ == "__main__":
    main()
