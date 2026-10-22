#!/usr/bin/env python3
"""Grade ecdsa-fail: build+run the candidate circuit with the pinned harness and
score it as avg_Toffoli x peak_qubits (lower is better).

DRAFT. The candidate `src/point_add.rs` is untrusted: it is assembled into the
trusted crate, then compiled and run as an unprivileged user in this no-network
container. The harness (`experiment` bin / main.rs) derives its test points by
Fiat-Shamir from the emitted op stream (un-gameable), validates correctness +
reversibility + forward-reverse + phase + end-state garbage, and prints the
metrics we parse below. Resource limits still need tuning against a real run.
"""

from __future__ import annotations

import json
import os
import re
import resource
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

CANDIDATE_PATH = Path(
    os.environ.get(
        "CANDIDATE_PATH",
        "/workspace/repo/src/point_add.rs",
    )
)
EVALUATOR_ROOT = Path(os.environ.get("EVALUATOR_ROOT", "/opt/evaluator"))
REWARD_PATH = Path(os.environ.get("REWARD_PATH", "/logs/verifier/reward.json"))
SCORE_PATH = Path(os.environ.get("SCORE_PATH", "/logs/verifier/score.json"))
BUILD_TIMEOUT = int(os.environ.get("BUILD_TIMEOUT", "1800"))   # seconds
RUN_TIMEOUT = int(os.environ.get("RUN_TIMEOUT", "1800"))       # seconds
# The baseline sim allocates ~15 GB, so the self-cap must be well above that;
# the real bound is the verifier container's memory (task.toml verifier.environment).
MEMORY_LIMIT = int(os.environ.get("MEMORY_LIMIT_BYTES", str(32 * 1024**3)))

# Lower is better, so an invalid/failed run gets a large sentinel score.
INVALID_SCORE = float(os.environ.get("INVALID_SCORE", "1e18"))

TOFFOLI_RE = re.compile(r"avg executed Toffoli\s*:\s*([0-9]+(?:\.[0-9]+)?)")
PEAK_RE = re.compile(r"peak live\s+([0-9]+)")


def atomic_write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as tmp:
        json.dump(value, tmp, indent=2, sort_keys=True)
        tmp.write("\n")
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)


def candidate_uid_gid() -> tuple[int, int]:
    import pwd

    account = pwd.getpwnam("candidate")
    return account.pw_uid, account.pw_gid


def limit_process() -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT, MEMORY_LIMIT))


def run_cargo(workdir: Path, uid: int, gid: int) -> subprocess.CompletedProcess[str]:
    """Compile + run the experiment bin as the unprivileged candidate user."""
    # Inherit the image environment (RUSTUP_HOME=/usr/local/rustup with the
    # pinned toolchain, CARGO_HOME=/opt/cargo with pre-fetched deps, PATH), and
    # only override where the candidate needs to write. Not inheriting these made
    # rustup look in $HOME/.rustup and try to download the toolchain -> fails
    # under --network none.
    env = {
        **os.environ,
        "HOME": str(workdir),
        "CARGO_TARGET_DIR": str(workdir / "target"),
        "RUSTFLAGS": "-C linker=gcc",
    }
    return subprocess.run(
        ["cargo", "run", "--release", "--offline", "--bin", "experiment"],
        cwd=workdir,
        env=env,
        user=uid,
        group=gid,
        preexec_fn=limit_process,
        capture_output=True,
        text=True,
        timeout=BUILD_TIMEOUT + RUN_TIMEOUT,
    )


def score_candidate(
    candidate_path: Path, workdir: Path = Path("/tmp/ecdsa-build")
) -> dict:
    """Assemble the crate, build+run the benchmark, and return the scored details.

    Shared scoring core: the one-shot verifier (main) and the eval sidecar
    (serve.py) both call this. Raises ValueError for a malformed candidate file
    (missing / symlink / empty); a build, correctness, or timeout failure is
    reported via the returned dict's `status`, not raised.
    """
    if candidate_path.is_symlink() or not candidate_path.is_file():
        raise ValueError(f"candidate must be a regular file: {candidate_path}")
    if candidate_path.stat().st_size == 0:
        raise ValueError("candidate must not be empty")

    uid, gid = candidate_uid_gid()
    if workdir.exists():
        shutil.rmtree(workdir)
    # Assemble the crate: trusted harness + the candidate's point_add.rs.
    shutil.copytree(EVALUATOR_ROOT, workdir)
    shutil.copyfile(candidate_path, workdir / "src" / "point_add.rs")
    for path in workdir.rglob("*"):
        os.chown(path, uid, gid)
    os.chown(workdir, uid, gid)

    started = time.monotonic()
    status = "ok"
    stdout = stderr = ""
    try:
        result = run_cargo(workdir, uid, gid)
        stdout, stderr = result.stdout, result.stderr
        if result.returncode != 0:
            status = "invalid"  # correctness/reversibility/phase/etc. failed
    except subprocess.TimeoutExpired:
        status = "timeout"

    toffoli = peak = None
    score = INVALID_SCORE
    if status == "ok":
        tof_match = TOFFOLI_RE.search(stdout)
        peak_match = PEAK_RE.search(stdout)
        if tof_match and peak_match:
            toffoli = float(tof_match.group(1))
            peak = int(peak_match.group(1))
            score = toffoli * peak
        else:
            status = "unparsed"

    return {
        "schema_version": 1,
        "metric": "ecdsafail_score",
        "direction": "minimize",
        "status": status,
        "score": score,
        "avg_toffoli": toffoli,
        "peak_qubits": peak,
        "elapsed_seconds": time.monotonic() - started,
        "stdout_tail": stdout[-4000:],
        "stderr_tail": stderr[-4000:],
    }


def main() -> None:
    try:
        details = score_candidate(CANDIDATE_PATH)
    except ValueError as error:
        raise SystemExit(str(error))
    atomic_write_json(SCORE_PATH, details)
    atomic_write_json(REWARD_PATH, {"ecdsafail_score": details["score"]})
    print(json.dumps({k: details[k] for k in ("status", "score", "avg_toffoli", "peak_qubits")}))


if __name__ == "__main__":
    main()
