"""Credential delivery and spending boundaries without any paid requests."""
import copy
from decimal import Decimal
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

from catalyst.common import CatalystError, write_json
from catalyst.evaluator import JobStore
from catalyst.live_provider import CodexAccess, encode_codex_access, decode_codex_access
from catalyst.model_access import CredentialChannel, CredentialInbox, take_worker_token
from catalyst.remote import fetch, request_body
from catalyst.worker import collect_usage

ROOT = Path(__file__).resolve().parents[1]
SECRET = "provider-secret-must-not-persist"


class ModelAccessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = JobStore(self.root / "service")
        with patch.dict(os.environ, {"CATALYST_LOCAL_TEST": "", "CATALYST_LOCAL_ECDSA": ""}):
            self.request = {**request_body(ROOT / "harnesses/ecdsa-research", "https://example.invalid"),
                            "request_id": str(uuid.uuid4())}
        self.evaluation = copy.deepcopy(self.request["evaluation"])

    def reply(self, *_):
        return {"id": "test-completion", "choices": [{"message": {"content": "research"}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120,
                          "prompt_tokens_details": {"cached_tokens": 3}}}

    def payload(self):
        return {"model": self.evaluation["model"]["name"], "messages": [{"role": "user", "content": "test"}],
                "max_completion_tokens": 100}

    def test_inbox_binds_single_delivery_to_job_and_never_persists_secret(self):
        inbox = CredentialInbox(self.store)
        identity = inbox.enqueue("owner", self.request, None, SECRET)
        self.assertEqual(inbox.enqueue("owner", self.request, None, SECRET), identity)
        with self.assertRaises(CatalystError):
            inbox.take(identity)  # The worker must have claimed the job.
        self.store.claim()
        self.assertEqual(inbox.take(identity), SECRET)
        self.assertEqual(inbox.enqueue("owner", self.request, None, SECRET), identity)
        with self.assertRaises(CatalystError):
            inbox.take(identity)  # A submit retry does not replenish spent access.
        for path in self.root.rglob("*"):
            if path.is_file():
                self.assertNotIn(SECRET.encode(), path.read_bytes())

    def test_expired_and_restarted_inboxes_fail_without_provider_requests(self):
        inbox = CredentialInbox(self.store, ttl=1)
        identity = inbox.enqueue("owner", self.request, None, SECRET)
        self.store.claim()
        with patch("catalyst.model_access.time.monotonic", return_value=float("inf")):
            with self.assertRaises(CatalystError):
                inbox.take(identity)
        self.assertEqual(inbox.entries, {})
        with self.assertRaises(CatalystError):
            CredentialInbox(self.store).take(identity)

    def test_private_socket_delivers_only_the_claimed_job_once(self):
        inbox = CredentialInbox(self.store)
        identity = inbox.enqueue("owner", self.request, None, SECRET)
        self.store.claim()
        channel = CredentialChannel(inbox)
        worker = socket.socket(fileno=channel.child.dup().detach())
        self.addCleanup(worker.close)
        self.addCleanup(channel.close)
        channel.start()
        self.assertEqual(take_worker_token(worker, identity), SECRET)
        with self.assertRaises(CatalystError):
            take_worker_token(worker, identity)
        self.assertEqual(inbox.entries, {})

    def test_credential_descriptor_is_delivered_to_a_real_child_process(self):
        import hashlib
        inbox = CredentialInbox(self.store)
        identity = inbox.enqueue("owner", self.request, None, SECRET)
        self.store.claim()
        channel = CredentialChannel(inbox)
        self.addCleanup(channel.close)
        script = (
            "import hashlib,socket,sys\n"
            "from catalyst.model_access import take_worker_token\n"
            "connection=socket.socket(fileno=int(sys.argv[1]))\n"
            "token=take_worker_token(connection,sys.argv[2])\n"
            "print(hashlib.sha256(token.encode()).hexdigest())\n"
        )
        process = subprocess.Popen(
            [sys.executable, "-c", script, str(channel.child.fileno()), identity],
            pass_fds=(channel.child.fileno(),), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={"PYTHONPATH": str(ROOT / "src")}, text=True,
        )
        channel.start()
        output, errors = process.communicate(timeout=10)
        self.assertEqual(process.returncode, 0, errors)
        self.assertEqual(output.strip(), hashlib.sha256(SECRET.encode()).hexdigest())
        self.assertNotIn(SECRET, output + errors)
        self.assertEqual(inbox.entries, {})

    def test_build_failure_discards_credential_before_handoff(self):
        inbox = CredentialInbox(self.store)
        identity = inbox.enqueue("owner", self.request, None, SECRET)
        self.store.claim()
        self.store.transition(identity, "failed", {"status": "failed"})
        inbox.sweep()
        self.assertEqual(inbox.entries, {})

    def test_codex_handoff_excludes_renewable_credentials(self):
        source = self.root / "auth.json"
        write_json(source, {"auth_mode": "chatgpt", "last_refresh": "2026-10-07T22:00:00Z", "tokens": {
            "access_token": SECRET, "id_token": "identity-token", "account_id": "test-account",
            "refresh_token": "renewable-must-stay-local"}})
        encoded = encode_codex_access(source)
        access = decode_codex_access(encoded)
        self.assertEqual(set(access), {"access_token", "id_token", "account_id", "last_refresh"})
        self.assertEqual(access["last_refresh"], "2026-10-07T22:00:00Z")
        self.assertEqual(access["access_token"], SECRET)
        self.assertNotIn("renewable-must-stay-local", repr(access))
        with self.assertRaises(CatalystError):
            decode_codex_access("not-a-login")

    @unittest.skipUnless(sys.platform == "linux", "Credential staging requires Linux tmpfs")
    def test_codex_access_is_staged_in_ram_and_cleaned(self):
        source = self.root / "auth.json"
        write_json(source, {"auth_mode": "chatgpt", "last_refresh": "2026-10-07T22:00:00Z", "tokens": {
            "access_token": SECRET, "id_token": "identity-token", "account_id": "test-account"}})
        with CodexAccess(self.evaluation, encode_codex_access(source)) as access:
            directory = access.directory
            self.assertEqual(directory.parent, Path("/dev/shm"))
            document = json.loads(access.auth_file.read_text())
            self.assertEqual(document["tokens"]["refresh_token"], "refresh-disabled-on-remote-worker")
            self.assertEqual(document["last_refresh"], "2026-10-07T22:00:00Z")
            self.assertEqual(access.auth_file.stat().st_mode & 0o777, 0o600)
        self.assertFalse(directory.exists())
        self.assertEqual(access.access, {})

    def test_fractional_microcredits_preserve_exact_cost_and_check_rounded_gateway_ledger(self):
        event = {"source": "gateway", "kind": "model.accounting", "request_id": "one",
                 "data": {"accounting_method": "gateway", "provider": "openai", "model": "gpt-5.6-sol",
                          "input_tokens": 100, "output_tokens": 20, "cached_input_tokens": 3,
                          "cache_write_input_tokens": 0, "normalized_usd": .001087, "billed_tokens": 117}}
        usage = self.root / "usage"
        usage.mkdir()
        (usage / "events.jsonl").write_text(json.dumps(event) + "\n")
        write_json(self.root / "record.json", {"data": {"usage": {
            "normalized_usd": .001087, "model_tokens": 117}}})
        self.evaluation["model"] = {"provider": "openai", "name": "gpt-5.6-sol"}
        ledger, total = collect_usage(self.root, self.evaluation)
        self.assertEqual(total, Decimal("0.0010865"))
        self.assertEqual(len(ledger), 1)
        self.assertEqual(ledger[0]["budget_tokens"], 117)
        write_json(self.root / "record.json", {"data": {"usage": {
            "normalized_usd": .001087, "model_tokens": 118}}})
        with self.assertRaisesRegex(CatalystError, "terminal counter"):
            collect_usage(self.root, self.evaluation)
        write_json(self.root / "record.json", {"data": {"usage": {
            "normalized_usd": .001087, "model_tokens": 117}}})
        event["data"]["normalized_usd"] = .002
        (usage / "events.jsonl").write_text(json.dumps(event) + "\n")
        with self.assertRaises(CatalystError):
            collect_usage(self.root, self.evaluation)

    def test_plain_http_cannot_transmit_provider_token(self):
        with patch("catalyst.remote.urllib.request.build_opener") as opener:
            with self.assertRaises(CatalystError):
                fetch("http://127.0.0.1:9999/evaluations", "session",
                      document=self.request, model_token=SECRET)
            opener.assert_not_called()


if __name__ == "__main__":
    unittest.main()
