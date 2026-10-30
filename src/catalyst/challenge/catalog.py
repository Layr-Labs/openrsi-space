"""Small pinned initial problem set and an ongoing, non-ranked development loop."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

from catalyst.common import CatalystError, safe_relative
from .paths import PROBLEM_SET, PROBLEM_DIRECTORIES

def git(root: Path, *args) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if result.returncode:
        raise CatalystError(result.stderr.strip() or "Git command failed.")
    return result.stdout.strip()



PROBLEM_RELEASES = {"v1": "ecdsa-fail/releases/v1.json"}


def initial_problems(*, release=None) -> list[dict]:
    filename = PROBLEM_RELEASES.get(release if release is not None else "v1")
    if filename is None:
        raise CatalystError("Unknown or retired problem release; choose " + ", ".join(PROBLEM_RELEASES) + ".")
    return json.loads((PROBLEM_SET / filename).read_text())["problems"]


def is_official_problem_set(problem_set) -> bool:
    return any(problem_set == initial_problems(release=release) for release in PROBLEM_RELEASES)


def get_problem(identity: str, *, release=None) -> dict:
    for problem in initial_problems(release=release):
        if problem["id"] == identity:
            return problem
    raise CatalystError("Unknown initial problem; run openrsi-space problem list.")


def problem_statement(identity: str) -> str:
    """Statements belong to the public challenge, independently of its runtime."""
    problem = get_problem(identity)
    return (PROBLEM_DIRECTORIES[problem["id"]] / "description.md").read_text()


def clone_problem(identity: str, destination: Path) -> dict:
    problem = get_problem(identity)
    if destination.exists():
        raise CatalystError(f"Destination already exists: {destination}")
    repository = problem["repository"]
    destination.parent.mkdir(parents=True, exist_ok=True)
    git(destination.parent, "clone", "--quiet", "--no-checkout", repository["url"], str(destination))
    git(destination, "checkout", "--quiet", "--detach", repository["commit"])
    return {"problem": identity, "workspace": str(destination), "commit": repository["commit"]}


def validate_workspace(problem: dict, workspace: Path) -> None:
    if git(workspace, "rev-parse", "HEAD") != problem["repository"]["commit"]:
        raise CatalystError("Workspace is not at this problem's pinned start/contract commit.")
    allowed = [safe_relative(item) for item in problem["candidate_paths"]]
    # Candidate source may change without resetting the workspace or deleting caches.
    changed = subprocess.run(["git", "-C", str(workspace), "diff", "--name-only", "-z", "HEAD"],
                             capture_output=True, check=True).stdout.decode().split("\0")
    for filename in filter(None, changed):
        if not any(filename == item or filename.startswith(item + "/") for item in allowed):
            raise CatalystError(f"Trusted problem file was modified: {filename}")
    untracked = subprocess.run(["git", "-C", str(workspace), "ls-files", "--others",
                                "--exclude-standard", "-z"], capture_output=True,
                               check=True).stdout.decode().split("\0")
    for filename in filter(None, untracked):
        # Upstream-declared ignored build caches are deliberately retained.
        if not any(filename == item or filename.startswith(item + "/") for item in allowed):
            raise CatalystError(f"Unexpected untracked file outside candidate paths: {filename}")


def develop(identity: str, workspace: Path, operation: str) -> int:
    problem = get_problem(identity)
    workspace = workspace.resolve()
    validate_workspace(problem, workspace)
    command = problem["setup_command"] if operation == "setup" else problem["check_command"]
    import os
    environment = dict(os.environ)
    print(f"{problem['title']}: {operation} (local development; not official evidence)", flush=True)
    if operation == "check":
        # A previous score must never make a failed or empty check look successful.
        (workspace / problem["score_path"]).unlink(missing_ok=True)
    result = subprocess.run(command, cwd=workspace, env=environment)
    if result.returncode == 0 and operation == "check":
        score_file = workspace / problem["score_path"]
        if not score_file.is_file():
            raise CatalystError("Verifier succeeded without producing the declared score file.")
        print(score_file.read_text())
    return result.returncode
