"""Read-only, per-run problem service. No credentials, evaluator or mutable state."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path

MAX_TASK_BYTES = 256 * 1024


def canonical(document):
    return json.dumps(document, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def load_document(path, expected_digest):
    with Path(path).open("rb") as source:
        raw = source.read(MAX_TASK_BYTES + 1)
    if len(raw) > MAX_TASK_BYTES:
        raise ValueError("Task document is too large.")
    document = json.loads(raw)
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise ValueError("Unsupported task document.")
    payload = canonical(document)
    if hashlib.sha256(payload).hexdigest() != expected_digest:
        raise ValueError("Task document does not match its pinned digest.")
    return payload


def handler_for(payload, digest):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, body):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Task-SHA256", digest)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/task":
                self.reply(200, payload)
            elif self.path == "/healthz":
                self.reply(200, b'{"status":"ok"}')
            else:
                self.reply(404, b'{"error":"not found"}')

        def do_POST(self):
            self.reply(405, b'{"error":"read-only service"}')

        do_PUT = do_POST
        do_PATCH = do_POST
        do_DELETE = do_POST

    return Handler


def main():
    digest = os.environ["TASK_SHA256"]
    payload = load_document(os.environ.get("TASK_DOCUMENT", "/data/task.json"), digest)
    with ThreadingHTTPServer(("0.0.0.0", 8091), handler_for(payload, digest)) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
