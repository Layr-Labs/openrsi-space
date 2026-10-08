"""One-evaluation provider credentials, kept only in API/worker process memory.

The inherited socket belongs to the supervised worker. It is never passed to
Docker, Dungeness, or harness subprocesses. Queue records contain no credentials.
"""
from __future__ import annotations

import json
import socket
import struct
import threading
import time

from .common import CatalystError
from .evaluator import APIError, identity

TEMPORARY_GRANT = "grant_temporary_provider"
TOKEN_HEADER = "X-Catalyst-Model-Token"
MAX_TOKEN_BYTES = 8192
MAX_MESSAGE_BYTES = 16384


def temporary_access(evaluation):
    return evaluation["llm_access"]["grant_id"] == TEMPORARY_GRANT


def validate_token(token):
    if (not isinstance(token, str) or not 8 <= len(token) <= MAX_TOKEN_BYTES
            or any(ord(character) < 33 or ord(character) > 126 for character in token)):
        raise APIError(400, "Supply a provider access token through the private token prompt.")


class CredentialInbox:
    """Atomic queue admission and one-time delivery to the trusted worker."""

    def __init__(self, store, *, ttl=3600):
        self.store = store
        self.ttl = ttl
        self.lock = threading.Lock()
        self.entries = {}

    def enqueue(self, owner, request, limits, token):
        validate_token(token)
        with self.lock:
            self._expire()
            # The same operation key always resolves to the existing job. A
            # repeat must not renew credentials after execution has started.
            with self.store.connect() as db:
                previous = db.execute(
                    "SELECT id,status FROM jobs WHERE owner=? AND request_id=?",
                    (owner, request["request_id"]),
                ).fetchone()
            evaluation_id = self.store.create(owner, request, limits)
            if previous is None or previous["status"] == "queued":
                if evaluation_id not in self.entries:
                    self.entries[evaluation_id] = (owner, token, time.monotonic() + self.ttl)
            return evaluation_id

    def _expire(self):
        now = time.monotonic()
        self.entries = {key: value for key, value in self.entries.items() if value[2] > now}

    def take(self, evaluation_id):
        identity(evaluation_id)
        with self.lock:
            self._expire()
            job = self.store.get(evaluation_id)
            entry = self.entries.get(evaluation_id)
            if (job["status"] != "building" or not temporary_access(job["request"]["evaluation"])
                    or entry is None or entry[0] != job["owner"]):
                raise CatalystError("Temporary model access is unavailable; no provider request was made.")
            del self.entries[evaluation_id]
            return entry[1]

    def close(self):
        with self.lock:
            self.entries.clear()

    def sweep(self):
        """Discard credentials after expiry or a build failure before handoff."""
        with self.lock:
            self._expire()
            if self.entries:
                with self.store.connect() as db:
                    active = {row["id"] for row in db.execute(
                        "SELECT id FROM jobs WHERE status IN ('queued','building')")}
                self.entries = {key: value for key, value in self.entries.items() if key in active}


def send_message(connection, document):
    payload = json.dumps(document, separators=(",", ":")).encode()
    if len(payload) > MAX_MESSAGE_BYTES:
        raise CatalystError("Invalid private worker message.")
    connection.sendall(struct.pack("!I", len(payload)) + payload)


def receive_message(connection):
    def exact(length):
        chunks = bytearray()
        while len(chunks) < length:
            chunk = connection.recv(length - len(chunks))
            if not chunk:
                raise EOFError
            chunks.extend(chunk)
        return bytes(chunks)

    length = struct.unpack("!I", exact(4))[0]
    if not 0 < length <= MAX_MESSAGE_BYTES:
        raise CatalystError("Invalid private worker message.")
    return json.loads(exact(length))


class CredentialChannel:
    def __init__(self, inbox):
        self.inbox = inbox
        self.parent, self.child = socket.socketpair()
        self.thread = threading.Thread(target=self._serve, daemon=True)

    def start(self):
        self.child.close()  # The worker inherited its own descriptor at spawn.
        self.thread.start()

    def _serve(self):
        try:
            while True:
                request = receive_message(self.parent)
                try:
                    if not isinstance(request, dict) or set(request) != {"evaluation_id"}:
                        raise CatalystError("Invalid private worker message.")
                    token = self.inbox.take(request["evaluation_id"])
                    response = {"token": token}
                except (CatalystError, ValueError, TypeError):
                    response = {"error": "Temporary model access is unavailable."}
                send_message(self.parent, response)
                # Do not retain the delivered credential while waiting for work.
                response = None
                token = None
        except (EOFError, OSError, ValueError, CatalystError):
            pass

    def close(self):
        self.child.close()
        try:
            self.parent.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.parent.close()
        if self.thread.is_alive():
            self.thread.join(timeout=2)
        self.inbox.close()


def take_worker_token(connection, evaluation_id):
    if connection is None:
        raise CatalystError("Temporary model access requires a supervised worker.")
    try:
        send_message(connection, {"evaluation_id": evaluation_id})
        response = receive_message(connection)
        token = response.get("token") if isinstance(response, dict) else None
        validate_token(token)
        return token
    except (EOFError, OSError, ValueError, CatalystError):
        raise CatalystError("Temporary model access is unavailable; no provider request was made.") from None
