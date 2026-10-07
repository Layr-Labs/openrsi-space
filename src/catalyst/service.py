"""Own the verification worker's lifetime alongside the HTTP server."""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from .common import CatalystError


@contextmanager
def termination_as_interrupt():
    def interrupt(*_):
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGTERM, interrupt)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


def signal_group(group, sig):
    try:
        os.killpg(group, sig)
    except ProcessLookupError:
        pass


def group_exists(group):
    try:
        os.killpg(group, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Darwin may report EPERM briefly while an orphaned group exits.
        # A denied probe does not establish that the group has disappeared.
        return True


class WorkerSupervisor:
    """Fail the service on worker loss; never automatically repeat an evaluation."""

    def __init__(self, store, config_path):
        self.store = store
        self.ready = False
        self.groups = set()
        self.buffer = b""
        self.log_path = store.root / "worker.log"
        self.log = self.log_path.open("a")
        self.log_path.chmod(0o600)
        self.read_fd, write_fd = os.pipe()
        os.set_blocking(self.read_fd, False)
        environment = {key: os.environ[key] for key in (
            "PATH", "HOME", "TMPDIR", "USER", "LOGNAME", "DOCKER_HOST", "DOCKER_CONTEXT",
        ) if key in os.environ}
        environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
        try:
            self.process = subprocess.Popen(
                [sys.executable, "-m", "catalyst.cli", "--state", str(store.root),
                 "worker", "--local-test", "--config", str(config_path.resolve()),
                 "--supervisor-fd", str(write_fd)],
                env=environment, stdin=subprocess.DEVNULL, stdout=self.log, stderr=subprocess.STDOUT,
                start_new_session=True, pass_fds=(write_fd,),
            )
        except BaseException:
            os.close(self.read_fd)
            self.log.close()
            raise
        finally:
            os.close(write_fd)

    def drain(self):
        while True:
            try:
                data = os.read(self.read_fd, 4096)
            except BlockingIOError:
                break
            if not data:
                break
            self.buffer += data
            while b"\n" in self.buffer:
                line, self.buffer = self.buffer.split(b"\n", 1)
                event = json.loads(line)
                if event["event"] == "ready":
                    self.ready = True
                elif event["event"] == "started":
                    self.groups.add(event["pid"])
                elif event["event"] == "stopped":
                    self.groups.discard(event["pid"])

    def check(self):
        self.drain()
        code = self.process.poll()
        if code is not None:
            raise CatalystError(f"Worker exited ({code}); service stopped. See {self.log_path}.")

    def wait_ready(self, timeout=10):
        deadline = time.monotonic() + timeout
        while True:
            self.check()
            if self.ready:
                return
            if time.monotonic() >= deadline:
                raise CatalystError(f"Worker did not become ready; see {self.log_path}.")
            time.sleep(.05)

    def close(self):
        self.drain()
        # Include independent Dungeness process groups if the worker died before
        # its own cleanup. The worker reports only trusted, directly spawned PIDs.
        groups = self.groups | {self.process.pid}
        signal_group(self.process.pid, signal.SIGINT)
        signalled = {self.process.pid}
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            self.drain()
            groups.update(self.groups)
            if self.process.poll() is not None:
                for group in groups - signalled:
                    signal_group(group, signal.SIGINT)
                    signalled.add(group)
            if not any(group_exists(group) for group in groups):
                break
            time.sleep(.05)
        for group in groups:
            if group_exists(group):
                signal_group(group, signal.SIGKILL)
        self.process.wait(timeout=5)
        os.close(self.read_fd)
        self.log.close()
        if self.ready:
            from .worker import worker_lock
            with worker_lock(self.store):
                self.store.recover_interrupted()
