from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from .catalog import Catalog
from .common import CatalystError, MAX_BUNDLE_BYTES, canonical, open_bundle
from .tiers import TIERS, tier


def handler_for(catalog: Catalog):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, body: bytes, status=200, content_type="application/json", filename=None):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            if content_type.startswith("text/html"):
                self.send_header("Content-Security-Policy",
                                 "default-src 'self'; script-src 'self'; style-src 'self'; "
                                 "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

        def json_response(self, value, status=200):
            self.send(canonical(value), status)

        def do_GET(self):
            try:
                route = urlsplit(self.path)
                path = unquote(route.path)
                params = {key: value[0] for key, value in parse_qs(route.query).items()}
                if path == "/api/catalog":
                    return self.json_response({"objects": catalog.list(params.get("kind")),
                                               "budget_tiers": [*TIERS, "best"]})
                if path == "/api/matrix":
                    budget = params.get("budget", "20")
                    return self.json_response(catalog.matrix(
                        params["problem"], params["version"], None if budget == "best" else tier(int(budget)),
                        params.get("model"), params.get("conditions")))
                parts = path.strip("/").split("/")
                if len(parts) == 5 and parts[:2] in (["api", "objects"], ["api", "bundles"]):
                    _, operation, kind, identity, version = parts
                    if operation == "objects":
                        obj = catalog.get(kind, identity, version)
                        snapshot, files = open_bundle(catalog.bundle_path(kind, identity, version).read_bytes())
                        obj["files"] = snapshot["files"]
                        if "instructions.md" in files:
                            obj["instructions"] = files["instructions.md"].decode(errors="replace")
                        if kind == "run":
                            obj["reports"] = catalog.reports(identity, version)
                        return self.json_response(obj)
                    catalog.get(kind, identity, version)
                    return self.send(catalog.bundle_path(kind, identity, version).read_bytes(),
                                     content_type="application/zip", filename=f"{kind}-{identity}-{version[:12]}.zip")
                static = {"": ("index.html", "text/html; charset=utf-8"),
                          "/": ("index.html", "text/html; charset=utf-8"),
                          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                          "/style.css": ("style.css", "text/css; charset=utf-8")}
                if path in static:
                    filename, mime = static[path]
                    return self.send((Path(__file__).parent / "static" / filename).read_bytes(), content_type=mime)
                self.json_response({"error": "Not found"}, 404)
            except (CatalystError, ValueError, KeyError) as error:
                self.json_response({"error": str(error)}, 400)

        def do_POST(self):
            try:
                # Browser writes require same-origin; the CLI deliberately has no Origin header.
                origin = self.headers.get("Origin")
                if origin and origin != "http://" + self.headers.get("Host", ""):
                    return self.json_response({"error": "Cross-origin writes are not supported."}, 403)
                length = int(self.headers.get("Content-Length", 0))
                if not 0 < length <= MAX_BUNDLE_BYTES:
                    return self.json_response({"error": "Invalid body size."}, 413)
                content = self.rfile.read(length)
                path = urlsplit(self.path).path
                mime = self.headers.get("Content-Type", "").split(";")[0]
                if path == "/api/publish" and mime == "application/zip":
                    return self.json_response(catalog.publish(content), 201)
                if path == "/api/reports" and mime == "application/json":
                    doc = json.loads(content)
                    return self.json_response(catalog.report(doc["run_id"], doc["run_version"],
                                                             doc["body"], doc.get("supporting_run")), 201)
                self.json_response({"error": "Unsupported endpoint or content type."}, 400)
            except (CatalystError, ValueError, KeyError) as error:
                self.json_response({"error": str(error)}, 400)
    return Handler


def serve(root: Path, port: int = 8765):
    server = ThreadingHTTPServer(("127.0.0.1", port), handler_for(Catalog(root)))
    print(f"Catalyst: http://127.0.0.1:{server.server_address[1]}", flush=True)
    print("Local, single-user catalog. All actions are performed through the CLI.", flush=True)
    try:
        server.serve_forever(poll_interval=.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
