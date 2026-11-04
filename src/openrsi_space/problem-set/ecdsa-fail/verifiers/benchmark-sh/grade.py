#!/usr/bin/env python3
"""Grade ecdsa-fail checkpoints using the upstream benchmark-sh interface by running its own
`benchmark.sh` -- we do not reimplement scoring.

The candidate is the whole `src/point_add/` module (untrusted). We assemble the
trusted harness (evaluator/, fetched at the checkpoint commit) + the candidate
module into a crate, then run the repo's `benchmark.sh`:

    build_circuit (UNTRUSTED, runs point_add::build())  -> ops.bin
    eval_circuit  (TRUSTED, never imports point_add)     -> score.json

`score.json` is `{"score": T*Q, "metrics": {"toffoli": T, "qubits": Q}}`. Lower
is better. This runs as an unprivileged user in the clean no-network verifier.

NOT YET COMPILE-TESTED: authored from the upstream sources; needs one real
Docker+Rust run (the ~15-20 GB simulator) to validate.
"""

from __future__ import annotations

import json
import os
import resource
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

# The candidate is a DIRECTORY (the src/point_add/ module) at these checkpoints.
CANDIDATE_PATH = Path(os.environ.get("CANDIDATE_PATH", "/workspace/repo/src/point_add"))
EVALUATOR_ROOT = Path(os.environ.get("EVALUATOR_ROOT", "/opt/evaluator"))
REWARD_PATH = Path(os.environ.get("REWARD_PATH", "/logs/verifier/reward.json"))
SCORE_PATH = Path(os.environ.get("SCORE_PATH", "/logs/verifier/score.json"))
BUILD_TIMEOUT = int(os.environ.get("BUILD_TIMEOUT", "1800"))
RUN_TIMEOUT = int(os.environ.get("RUN_TIMEOUT", "1800"))
MEMORY_LIMIT = int(os.environ.get("MEMORY_LIMIT_BYTES", str(32 * 1024**3)))
INVALID_SCORE = float(os.environ.get("INVALID_SCORE", "1e18"))


def atomic_write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as tmp:
        json.dump(value, tmp, indent=2, sort_keys=True)
        tmp.write("\n")
        # Harbor copies these root-produced results back to an unprivileged
        # host worker. Keep the score readable without making it writable.
        os.fchmod(tmp.fileno(), 0o644)
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)


def candidate_uid_gid() -> tuple[int, int]:
    import pwd

    account = pwd.getpwnam("candidate")
    return account.pw_uid, account.pw_gid


def limit_process() -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT, MEMORY_LIMIT))


def run_benchmark(workdir: Path, uid: int, gid: int) -> subprocess.CompletedProcess[str]:
    """Run the upstream benchmark.sh as the unprivileged candidate user."""
    env = {
        **os.environ,
        "HOME": str(workdir),
        "CARGO_TARGET_DIR": str(workdir / "target"),
        "CARGO_NET_OFFLINE": "true",
        "RUSTFLAGS": "-C linker=gcc",
    }
    return subprocess.run(
        ["bash", "./benchmark.sh"],
        cwd=workdir,
        env=env,
        user=uid,
        group=gid,
        preexec_fn=limit_process,
        capture_output=True,
        text=True,
        timeout=BUILD_TIMEOUT + RUN_TIMEOUT,
    )


def score_candidate(candidate_dir: Path, workdir: Path = Path("/tmp/ecdsa-build")) -> dict:
    """Assemble the crate (trusted harness + candidate module), run benchmark.sh,
    and return the parsed score. Shared by the one-shot verifier and serve.py."""
    if candidate_dir.is_symlink() or not candidate_dir.is_dir():
        raise ValueError(f"candidate must be a directory (the point_add module): {candidate_dir}")

    uid, gid = candidate_uid_gid()
    if workdir.exists():
        shutil.rmtree(workdir)
    shutil.copytree(EVALUATOR_ROOT, workdir)
    # Overlay the candidate module, replacing any placeholder point_add in the harness.
    dest = workdir / "src" / "point_add"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(candidate_dir, dest)
    for path in workdir.rglob("*"):
        os.chown(path, uid, gid)
    os.chown(workdir, uid, gid)

    started = time.monotonic()
    status = "ok"
    stdout = stderr = ""
    try:
        result = run_benchmark(workdir, uid, gid)
        stdout, stderr = result.stdout, result.stderr
        if result.returncode != 0:
            status = "invalid"  # build_circuit failed or eval_circuit rejected the circuit
    except subprocess.TimeoutExpired:
        status = "timeout"

    toffoli = peak = None
    score = INVALID_SCORE
    if status == "ok":
        score_file = workdir / "score.json"
        try:
            parsed = json.loads(score_file.read_text())
            metrics = parsed.get("metrics", {})
            toffoli = float(metrics["toffoli"])
            peak = int(metrics["qubits"])
            score = float(parsed["score"])
        except (OSError, ValueError, KeyError, TypeError):
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
