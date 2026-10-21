"""Read-only, per-run problem service. No credentials, evaluator or mutable state."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil

MAX_TASK_BYTES = 256 * 1024
MEDIA_TYPE = r"[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*"
PART = r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}"
RESOURCE_PATH = rf"/{PART}(?:/{PART})?/(?:description|knowledge-base|resources/{PART})"


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


def load_files(payload, root):
    """Validate the complete immutable attachment set before accepting requests."""
    document = json.loads(payload)
    entries = document.get("attachments", [])
    if not isinstance(entries, list) or len(entries) > 64:
        raise ValueError("Invalid task attachments.")
    files = {}
    total = 0
    for entry in entries:
        name = entry.get("name", "")
        if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", name)
                or "/task/files/" + name in files or type(entry.get("bytes")) is not int
                or not 0 < entry["bytes"] <= 32 * 1024 * 1024
                or not isinstance(entry.get("media_type"), str)
                or not re.fullmatch(MEDIA_TYPE, entry["media_type"])):
            raise ValueError("Invalid task attachment.")
        path = root / name
        if (root.is_symlink() or path.is_symlink() or not path.is_file()
                or path.stat().st_size != entry["bytes"]):
            raise ValueError("Task attachment missing or changed.")
        with path.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != entry.get("sha256"):
                raise ValueError("Task attachment digest mismatch.")
        files["/task/files/" + name] = (path, entry)
        paths = entry.get("paths", [])
        if not isinstance(paths, list):
            raise ValueError("Invalid task resource routes.")
        for route in paths:
            if not isinstance(route, str) or not re.fullmatch(RESOURCE_PATH, route) or route in files:
                raise ValueError("Invalid or duplicate task resource route.")
            files[route] = (path, entry)
        total += entry["bytes"]
    if total > 256 * 1024 * 1024:
        raise ValueError("Task attachments exceed size limit.")
    if entries and {p.name for p in root.iterdir()} != {e["name"] for e in entries}:
        raise ValueError("Unexpected task attachment.")
    return files


def handler_for(payload, digest, files=None):
    files = files or {}
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
            elif self.path in files:
                path, entry = files[self.path]
                self.send_response(200)
                self.send_header("Content-Type", entry["media_type"])
                self.send_header("Content-Length", str(entry["bytes"]))
                self.send_header("X-Content-SHA256", entry["sha256"])
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Disposition", f'attachment; filename="{entry["name"]}"')
                self.end_headers()
                with path.open("rb") as source:
                    shutil.copyfileobj(source, self.wfile, length=1024 * 1024)
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
    path = Path(os.environ.get("TASK_DOCUMENT", "/data/task.json"))
    payload = load_document(path, digest)
    files = load_files(payload, path.parent / "files")
    with ThreadingHTTPServer(("0.0.0.0", 8091), handler_for(payload, digest, files)) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
