"""Private local state and locks for resumable submissions."""
from contextlib import contextmanager
import fcntl
from pathlib import Path
from catalyst.common import CatalystError, write_json

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


def private_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    write_json(path, value)
    path.chmod(0o600)
