"""Adapt Codex's request envelopes to the assigned Responses gateway.

Omit session telemetry, use default reasoning-context handling, and place inline
tool declarations in the tools field. Reasoning effort remains unchanged.
Tool definitions, instructions and model conversation content remain unchanged.
The assigned gateway still validates all requests and meters all model usage.
"""
from contextlib import contextmanager
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from urllib.parse import urlsplit


@contextmanager
def compatible_gateway(base_url):
    target = urlsplit(base_url)
    if target.scheme != "http" or target.username or target.password or target.query or target.fragment:
        raise ValueError("Expected the assigned internal HTTP gateway.")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            if self.path not in {"/v1/responses", "/v1/responses/compact"}:
                self.send_error(404)
                return
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 16 * 1024 * 1024:
                self.send_error(413)
                return
            payload = json.loads(self.rfile.read(size))
            payload.pop("client_metadata", None)
            reasoning = payload.get("reasoning")
            if isinstance(reasoning, dict) and reasoning.get("context") == "all_turns":
                reasoning.pop("context")
            if isinstance(payload.get("input"), list):
                history = []
                for item in payload["input"]:
                    if (isinstance(item, dict) and item.get("type") == "additional_tools"
                            and set(item) <= {"type", "id", "role", "tools"}
                            and item.get("role") == "developer"
                            and isinstance(item.get("tools"), list)):
                        payload.setdefault("tools", []).extend(item["tools"])
                    else:
                        history.append(item)
                payload["input"] = history
            connection = http.client.HTTPConnection(target.hostname, target.port, timeout=600)
            try:
                connection.request(
                    "POST", target.path.rstrip("/") + self.path.removeprefix("/v1"),
                    body=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json", "Accept": "text/event-stream",
                             "Authorization": "Bearer testbed"},
                )
                response = connection.getresponse()
                self.send_response(response.status)
                self.send_header("Content-Type", response.getheader("Content-Type", "application/json"))
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True
                while chunk := response.read1(65536):
                    self.wfile.write(chunk)
                    self.wfile.flush()
            finally:
                connection.close()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
