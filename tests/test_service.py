"""Real server/worker process lifecycle tests; no Docker or model requests."""
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid

from catalyst.common import write_json
from catalyst.evaluator import JobStore
from catalyst.remote import PROTOCOL, judge_input
from catalyst.service import WorkerSupervisor
from catalyst.worker import worker_lock

PROJECT = Path(__file__).resolve().parents[1]


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / "service"
        write_json(self.root / "auth.json", {"mode": "local-test", "tokens": {}, "grants": {}})
        write_json(self.root / "problems.json", [])
        write_json(self.root / "worker.json", {
            "mode": "local-test", "problem_set": str(self.root / "problems.json"),
        })
        self.store = JobStore(self.state)
        self.processes = []
        self.logs = []
        self.addCleanup(self.stop_all)

    def start(self, port=0):
        log_path = self.root / f"service-{len(self.processes)}.log"
        log = log_path.open("w")
        self.logs.append(log)
        process = subprocess.Popen(
            [sys.executable, "-m", "catalyst.cli", "--state", str(self.state),
             "evaluator-serve", "--local-test", "--auth-file", str(self.root / "auth.json"),
             "--problem-set", str(self.root / "problems.json"), "--port", str(port)],
            cwd=PROJECT, env={**os.environ, "PYTHONPATH": str(PROJECT / "src")},
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
        self.processes.append(process)
        return process, log_path

    def ready(self, process, log_path):
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            output = log_path.read_text()
            self.assertIsNone(process.poll(), output)
            port = re.search(r"verification API: http://127.0.0.1:(\d+)", output)
            worker = re.search(r"Managed worker: PID (\d+)", output)
            if port and worker:
                return int(port.group(1)), int(worker.group(1))
            time.sleep(.025)
        self.fail("Service never became ready: " + log_path.read_text())

    def stop_all(self):
        for process in self.processes:
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
                try:
                    process.wait(timeout=40)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        for log in self.logs:
            log.close()

    def assert_stopped(self, port, worker_pid):
        with self.assertRaises(ProcessLookupError):
            os.kill(worker_pid, 0)
        with self.assertRaises(OSError):
            socket.create_connection(("127.0.0.1", port), timeout=.3)

    def test_service_owns_worker_and_handles_interrupt_and_termination(self):
        for sig in (signal.SIGINT, signal.SIGTERM):
            with self.subTest(signal=sig):
                process, log = self.start()
                port, worker_pid = self.ready(process, log)
                self.assertNotEqual(worker_pid, process.pid)
                process.send_signal(sig)
                self.assertEqual(process.wait(timeout=10), 0, log.read_text())
                self.assert_stopped(port, worker_pid)
                with worker_lock(self.store):
                    pass  # Shutdown releases the worker lock, allowing a clean restart.

    def test_worker_crash_stops_api_and_marks_interrupted_job_failed(self):
        process, log = self.start()
        port, worker_pid = self.ready(process, log)
        # Pause the owned worker before adding an already-started job.
        os.kill(worker_pid, signal.SIGSTOP)
        request = {"request_id": str(uuid.uuid4()), "protocol": PROTOCOL,
                   "source": {"digest": "a" * 64}, "evaluation": {},
                   "problem_set": [], "pricing": {}, "judge": judge_input(None),
                   "evidence_mode": "local-test"}
        identity = self.store.create("fixture-owner", request)
        self.store.claim()
        queued = self.store.create("fixture-owner", {**request, "request_id": str(uuid.uuid4())})
        os.kill(worker_pid, signal.SIGKILL)
        self.assertEqual(process.wait(timeout=10), 1)
        self.assertIn("Worker exited", log.read_text())
        self.assert_stopped(port, worker_pid)
        self.assertEqual(self.store.get(identity)["status"], "failed")
        self.assertEqual(self.store.get(queued)["status"], "queued")

    def test_existing_worker_is_not_replaced_or_stopped(self):
        with worker_lock(self.store):
            process, log = self.start()
            self.assertEqual(process.wait(timeout=10), 1)
            self.assertNotIn("verification API:", log.read_text())
            self.assertIn("already owns", (self.state / "worker.log").read_text())

    def test_invalid_worker_configuration_fails_before_serving(self):
        write_json(self.root / "worker.json", {"mode": "remote"})
        process, log = self.start()
        self.assertEqual(process.wait(timeout=10), 1)
        self.assertIn("must match", log.read_text())
        self.assertFalse((self.state / "worker.log").exists())

    def test_occupied_port_does_not_start_worker(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            process, log = self.start(listener.getsockname()[1])
            self.assertEqual(process.wait(timeout=10), 1)
            self.assertNotIn("Managed worker", log.read_text())
            self.assertFalse((self.state / "worker.log").exists())

    def test_crashed_worker_execution_group_is_stopped(self):
        # Use the real worker's subprocess tracking with a sleeping command,
        # without invoking Docker. Kill the worker before it can clean up.
        helper = self.root / "sleeping-worker.py"
        helper.write_text(
            "import os, sys\nfrom pathlib import Path\nfrom catalyst import worker\n"
            "worker._SUPERVISOR_FD = int(sys.argv[1])\n"
            "worker.notify_supervisor('ready')\n"
            "worker.run_command([sys.executable, '-c', 'import time; time.sleep(60)'], "
            "Path.cwd(), dict(os.environ), Path(sys.argv[2]), 70)\n")
        real_popen = subprocess.Popen

        def launch(command, **kwargs):
            fd = command[command.index("--supervisor-fd") + 1]
            return real_popen([sys.executable, str(helper), fd, str(self.root / "command.log")], **kwargs)

        with patch("catalyst.service.subprocess.Popen", side_effect=launch):
            supervisor = WorkerSupervisor(self.store, self.root / "worker.json")
        try:
            supervisor.wait_ready()
            deadline = time.monotonic() + 5
            while not supervisor.groups and time.monotonic() < deadline:
                supervisor.drain()
                time.sleep(.01)
            self.assertTrue(supervisor.groups, "Worker did not report the spawned process group.")
            groups = set(supervisor.groups)
            supervisor.process.kill()
            supervisor.process.wait(timeout=5)
        finally:
            supervisor.close()
        for group in groups:
            with self.assertRaises(ProcessLookupError):
                os.killpg(group, 0)
