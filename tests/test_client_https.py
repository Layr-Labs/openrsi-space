"""Real loopback TLS handshakes with disposable certificates and synthetic secrets."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from catalyst.client import transport
from catalyst.client.evaluations import RemoteClient
from catalyst.common import CatalystError
from catalyst.credentials import TOKEN_HEADER

EVALUATION = "12345678-1234-4234-8234-123456789abc"
SOLVER = "cys_synthetic-solver-secret"
MODEL = "synthetic-model-secret-never-real"
BODY = "synthetic-request-body"


class CredentialURLTests(unittest.TestCase):
    def test_plaintext_remote_bearers_are_rejected_before_network_access(self):
        with patch.object(transport.urllib.request, "build_opener") as opener:
            for bearer in (SOLVER, "ykn_synthetic-key", "synthetic-legacy-bearer"):
                for operation in (
                    lambda: transport.fetch("http://verifier.invalid/evaluations", bearer, document={}),
                    lambda: transport.solver_fetch("http://verifier.invalid", "/evaluations", bearer, document={}),
                ):
                    with self.subTest(bearer=bearer), self.assertRaisesRegex(CatalystError, "HTTPS"):
                        operation()
            opener.assert_not_called()

    def test_model_access_is_limited_to_exact_https_submission_and_renewal_routes(self):
        with patch.object(transport.urllib.request, "build_opener") as opener:
            urls = [
                "http://127.0.0.1/evaluations", "http://localhost/evaluations",
                "http://[::1]/evaluations", "https://verifier.invalid/auth/yukon",
                "https://verifier.invalid/evaluations?next=/other",
                "https://verifier.invalid/evaluations#fragment",
                "https://user@verifier.invalid/evaluations",
                f"https://verifier.invalid/evaluations/{EVALUATION}",
                f"https://verifier.invalid/evaluations/{EVALUATION}/credentials/",
                f"https://verifier.invalid/evaluations/{EVALUATION}/credentials?next=/other",
                "https://verifier.invalid/evaluations/not-a-uuid/credentials",
                f"https://verifier.invalid/evaluations/{EVALUATION.upper()}/credentials",
                f"https://verifier.invalid/evaluations/{EVALUATION}/%63redentials",
            ]
            for url in urls:
                with self.subTest(url=url), self.assertRaises(CatalystError):
                    transport.fetch(url, SOLVER, document={}, model_token=MODEL)
            opener.assert_not_called()


@unittest.skipUnless(shutil.which("openssl"), "OpenSSL CLI is required for disposable TLS fixtures")
class ClientHTTPSTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="catalyst-test-tls-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        (cls.root / "empty-ca-dir").mkdir()

        def openssl(*args):
            subprocess.run(["openssl", *args], cwd=cls.root, check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)

        for name in ("ca", "unrelated-ca"):
            openssl("req", "-new", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
                    "-keyout", f"{name}.key", "-out", f"{name}.pem", "-subj", f"/CN=Synthetic {name}",
                    "-addext", "basicConstraints=critical,CA:TRUE",
                    "-addext", "keyUsage=critical,keyCertSign,cRLSign")
        (cls.root / "index").touch()
        (cls.root / "serial").write_text("1000\n")
        (cls.root / "newcerts").mkdir()
        for name,host,end in (("valid", "IP:127.0.0.1", "20990101000000Z"),
                              ("wrong-host", "DNS:another.example.invalid", "20990101000000Z"),
                              ("expired", "IP:127.0.0.1", "20200102000000Z")):
            openssl("req", "-new", "-newkey", "rsa:2048", "-nodes", "-keyout", f"{name}.key",
                    "-out", f"{name}.csr", "-subj", f"/CN=Synthetic {name}")
            config = f"""[ca]
default_ca=authority
[authority]
database=index
serial=serial
new_certs_dir=newcerts
certificate=ca.pem
private_key=ca.key
default_md=sha256
policy=policy
unique_subject=no
[policy]
commonName=supplied
[leaf]
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName={host}
"""
            (cls.root / "ca.cnf").write_text(config)
            openssl("ca", "-batch", "-config", "ca.cnf", "-extensions", "leaf", "-in", f"{name}.csr",
                    "-out", f"{name}.pem", "-startdate", "20200101000000Z", "-enddate", end)

    def setUp(self):
        transport._solver_sessions.clear()
        self.addCleanup(transport._solver_sessions.clear)
        # Use the actual default urllib/OpenSSL verification path, with a test CA.
        self.environment = patch.dict(os.environ, {
            "SSL_CERT_FILE": str(self.root / "ca.pem"), "SSL_CERT_DIR": str(self.root / "empty-ca-dir"),
            "NO_PROXY": "*", "no_proxy": "*", "HTTP_PROXY": "", "HTTPS_PROXY": "",
            "ALL_PROXY": "", "http_proxy": "", "https_proxy": "", "all_proxy": "",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)

    @contextmanager
    def server(self, certificate="valid", *, redirect=None, status=200):
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                requests.append({"path": self.path, "headers": self.headers, "body": body})
                self.send_response(status)
                if redirect:
                    self.send_header("Location", redirect)
                self.end_headers()
                self.wfile.write(json.dumps({"evaluation_id": EVALUATION, "status": "queued"}).encode())
            do_GET = do_POST
            def log_message(self, *_):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        if certificate:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(self.root / f"{certificate}.pem", self.root / f"{certificate}.key")
            server.socket = context.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        thread.start()
        try:
            yield f"{'https' if certificate else 'http'}://127.0.0.1:{server.server_port}", requests
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())

    def test_valid_certificate_accepts_the_original_credential_request(self):
        with self.server() as (url, requests):
            transport.fetch(url + "/evaluations", SOLVER, document={"canary": BODY}, model_token=MODEL)
            self.assertEqual(len(requests), 1)
            self.assertEqual(requests[0]["headers"]["Authorization"], f"Bearer {SOLVER}")
            self.assertEqual(requests[0]["headers"][TOKEN_HEADER], MODEL)
            self.assertEqual(json.loads(requests[0]["body"]), {"canary": BODY})

    def test_bad_certificates_reject_login_submission_and_renewal_before_http(self):
        for certificate,trust in (("expired", "ca"), ("wrong-host", "ca"), ("valid", "unrelated-ca")):
            with self.subTest(certificate=certificate, trust=trust), \
                    patch.dict(os.environ, {"SSL_CERT_FILE": str(self.root / f"{trust}.pem")}), \
                    self.server(certificate) as (url, requests):
                for route,model in (("/auth/yukon", None), ("/evaluations", MODEL),
                                    (f"/evaluations/{EVALUATION}/credentials", MODEL)):
                    with self.assertRaisesRegex(CatalystError, "TLS certificate verification failed") as raised:
                        transport.fetch(url + route, SOLVER, document={"canary": BODY}, model_token=model)
                    self.assertIn("do not disable TLS verification", str(raised.exception))
                    for secret in (SOLVER, MODEL, BODY):
                        self.assertNotIn(secret, str(raised.exception))
                self.assertEqual(requests, [])

    def test_real_renewal_client_uses_the_https_job_credential_route(self):
        with self.server() as (url, requests), tempfile.TemporaryDirectory() as state, \
                patch.dict(os.environ, {"CATALYST_EVALUATOR_URL": url}):
            client = RemoteClient(Path(state), bearer=SOLVER)
            self.assertEqual(client.renew_access(EVALUATION, MODEL), {"evaluation_id": EVALUATION, "status": "queued"})
            self.assertEqual(len(requests), 1)
            self.assertEqual(requests[0]["path"], f"/evaluations/{EVALUATION}/credentials")
            self.assertEqual(requests[0]["headers"][TOKEN_HEADER], MODEL)
            self.assertNotIn(MODEL.encode(), requests[0]["body"])
            for path in Path(state).rglob("*"):
                if path.is_file():
                    self.assertNotIn(MODEL.encode(), path.read_bytes())

    def test_plaintext_model_submission_is_rejected_before_yukon_login(self):
        with self.server(certificate=None) as (url, requests):
            with self.assertRaisesRegex(CatalystError, "HTTPS"):
                transport.solver_fetch(url, "/evaluations", "ykn_synthetic-key", document={}, model_token=MODEL)
            self.assertEqual(requests, [])
            # Explicit loopback fixtures still work without a real model token.
            transport.fetch(url + "/healthz", SOLVER)
            self.assertEqual(len(requests), 1)

    def test_redirects_do_not_forward_credentials_or_request_bodies(self):
        for target_certificate in (None, "valid"):
            with self.server(target_certificate) as (target, destination):
                for status in (301, 302, 303, 307, 308):
                    with self.subTest(target=target_certificate, status=status), \
                            self.server(redirect=target + "/evaluations", status=status) as (url, source):
                        with self.assertRaises(CatalystError):
                            transport.fetch(url + "/evaluations", SOLVER,
                                            document={"canary": BODY}, model_token=MODEL)
                        self.assertEqual(len(source), 1)
                        self.assertEqual(destination, [])
