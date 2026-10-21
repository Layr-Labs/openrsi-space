"""Safe copying and locking for candidate snapshots."""
from contextlib import contextmanager
import fcntl
from pathlib import Path
import shutil


def candidate_path(task):
    workspace = Path(task["workspace"]).resolve()
    paths = task["candidate_paths"]
    if len(paths) != 1:
        raise ValueError("Checkpoint helper requires exactly one assigned candidate path.")
    relative = Path(paths[0])
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ValueError("Candidate must be a relative path beneath the workspace.")
    target = workspace / relative
    if any(p.is_symlink() for p in [target, *target.parents] if p != workspace):
        raise ValueError("Candidate path must not contain symlinks.")
    if not target.resolve().is_relative_to(workspace) or target.resolve() == workspace:
        raise ValueError("Candidate must be beneath the workspace.")
    return target


def copy_candidate(source, destination):
    entries = [source, *source.rglob("*")] if source.is_dir() else [source]
    size = 0
    for entry in entries:
        if entry.is_symlink() or not (entry.is_file() or entry.is_dir()):
            raise ValueError("Candidate must contain only regular files and directories.")
        if entry.is_file():
            size += entry.stat().st_size
        if size > 64 * 1024 * 1024:
            raise ValueError("Checkpoint exceeds 64 MiB.")
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        shutil.copy2(source, destination)


@contextmanager
def locked(state):
    with (state / "lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield
