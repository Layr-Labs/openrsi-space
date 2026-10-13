"""Artifact ownership, immutable exports, explicit sharing and object-storage contracts."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import urllib.request
import zipfile

from catalyst.artifacts import PROTOCOL, sanitized, seal
from catalyst.artifact_storage import ArtifactStorage
from catalyst.common import CatalystError, read_json, write_json
from catalyst.remote import RemoteClient, fetch
from test_evaluator import EvaluatorFixture


class ArtifactTests(EvaluatorFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        environment = patch.dict(os.environ, {
            "CATALYST_EVALUATOR_URL": f"http://127.0.0.1:{self.server.server_port}",
        })
        environment.start()
        self.addCleanup(environment.stop)

    def prepare(self):
        identity = self.complete()
        folder = self.store.trace_path(identity).parent
        # Fixture completion exported an empty run; simulate a real retained run
        # before its first export rather than changing a sealed production bundle.
        (folder / "artifact-export.json").unlink()
        run = self.root / "worker/evaluations/run"
        run.mkdir(parents=True)
        write_json(folder / "runtime.json", {"record_path": str(run / "record.json")})
        write_json(run / "record.json", {"model": "fixture", "access_token": "never-export-this"})
        (run / "usage").mkdir()
        write_json(run / "usage/summary.json", {"normalized_usd": .25})
        (run / "usage/events.jsonl").write_text(
            '{"authorization":"Bearer never-export-that","event":"tool"}\n'
            '{"content":"keep this research output","refresh_token":"also-private"}\n')
        agent = run / "harbor/job/trial/agent"
        agent.mkdir(parents=True)
        (agent / "harness-output.txt").write_text("baseline checked\nAPI_KEY=private-key\n")
        (agent / "auth.json").write_text("MUST NOT BE PACKAGED")
        (folder / "candidate/src/point_add").mkdir(parents=True)
        (folder / "candidate/src/point_add/mod.rs").write_text("pub fn build() {}")
        return identity, folder, run

    def test_owner_download_has_original_harness_and_recorded_evidence(self):
        identity, folder, run = self.prepare()
        status, manifest = self.http(f"/evaluations/{identity}/artifacts")
        self.assertEqual(status, 200)
        self.assertEqual(manifest["sharing"]["harness"], False)
        self.assertEqual(manifest["sharing"]["traces"], False)
        self.assertEqual(manifest["missing"], [])
        client = RemoteClient(self.root / "client", bearer="alice-token")
        client.base = f"http://127.0.0.1:{self.server.server_port}"
        output = self.root / "complete.zip"
        received = client.download_artifact(identity, "complete", output)
        self.assertEqual(hashlib.sha256(output.read_bytes()).hexdigest(), received["sha256"])
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(archive.read("harness.zip"), base64.b64decode(self.request["source"]["archive_base64"]))
            self.assertIn("dungeness/record.json", archive.namelist())
            self.assertIn("candidate/src/point_add/mod.rs", archive.namelist())
            self.assertIn("dungeness/harbor/job/trial/agent/harness-output.txt", archive.namelist())
            self.assertNotIn("llm_access", json.loads(archive.read("evaluation.json")))
            for name in archive.namelist():
                if name != "harness.zip":
                    self.assertNotIn("auth.json", name)
                    self.assertNotIn(b"never-export", archive.read(name))
                    self.assertNotIn(b"also-private", archive.read(name))
                    self.assertNotIn(b"private-key", archive.read(name))
            self.assertEqual(json.loads(archive.read("dungeness/record.json"))["access_token"], "[REDACTED]")
        first = received["sha256"]
        (run / "record.json").write_text("{}")
        second = client.download_artifact(identity, "complete", output)
        self.assertEqual(second["sha256"], first)  # Exported bytes are immutable.

    def test_other_owners_workflows_and_anonymous_readers_cannot_read_or_publish(self):
        identity, _, _ = self.prepare()
        for token in ("bob-token", "workflow-token", ""):
            for suffix in ("artifacts", "artifacts/complete", "artifacts/complete/content", "sharing"):
                status, _ = self.http(f"/evaluations/{identity}/{suffix}", token=token)
                self.assertIn(status, (401, 404))
            status, _ = self.http(f"/evaluations/{identity}/sharing", token=token,
                                  body={"protocol": PROTOCOL, "harness": True, "license": "MIT"})
            self.assertIn(status, (401, 404))
        self.assertEqual(self.http(f"/public/evaluations/{identity}/artifacts", token="")[0], 404)

    def test_separate_publication_license_review_and_unpublish(self):
        identity, _, _ = self.prepare()
        route = f"/evaluations/{identity}/sharing"
        public = f"/public/evaluations/{identity}/artifacts"
        self.assertEqual(self.http(route, body={"protocol": PROTOCOL, "harness": True})[0], 400)
        self.assertEqual(self.http(route, body={"protocol": PROTOCOL, "traces": True})[0], 400)
        status, _ = self.http(route, body={"protocol": PROTOCOL, "harness": True, "license": "MIT"})
        self.assertEqual(status, 200)
        status, manifest = self.http(public, token="")
        self.assertEqual(status, 200)
        self.assertEqual(set(manifest["artifacts"]), {"harness"})
        self.assertNotIn("storage", json.dumps(manifest))
        self.assertEqual(self.http(public + "/traces", token="")[0], 404)
        self.assertEqual(self.http(public + "/complete", token="")[0], 404)
        with urllib.request.urlopen(
                f"http://127.0.0.1:{self.server.server_port}/public/evaluations/{identity}") as page:
            self.assertIn(b"Evaluated harness source", page.read())
            self.assertIn("default-src 'none'", page.headers["Content-Security-Policy"])
        with urllib.request.urlopen(
                f"http://127.0.0.1:{self.server.server_port}{public}/harness/content") as archive:
            self.assertEqual(archive.read(), base64.b64decode(self.request["source"]["archive_base64"]))
        status, _ = self.http(route, body={"protocol": PROTOCOL, "traces": True, "traces_reviewed": True})
        self.assertEqual(status, 200)
        self.assertEqual(set(self.http(public, token="")[1]["artifacts"]), {"harness", "traces"})
        status, _ = self.http(route, body={"protocol": PROTOCOL, "harness": False})
        self.assertEqual(status, 200)
        self.assertEqual(set(self.http(public, token="")[1]["artifacts"]), {"traces"})
        self.http(route, body={"protocol": PROTOCOL, "traces": False})
        self.assertEqual(self.http(public, token="")[0], 404)
        self.assertEqual(self.http(public + "/harness/content", token="")[0], 404)

    def test_no_following_symlink_or_outside_run_root(self):
        identity, folder, run = self.prepare()
        outside = self.root / "secret.txt"
        outside.write_text("private")
        (run / "record.json").unlink()
        (run / "record.json").symlink_to(outside)
        self.assertEqual(self.http(f"/evaluations/{identity}/artifacts")[0], 400)
        write_json(folder / "runtime.json", {"record_path": str(outside)})
        self.assertEqual(self.http(f"/evaluations/{identity}/artifacts")[0], 400)

    def test_json_jsonl_and_private_keys_redact_without_corrupting_records(self):
        raw = b'{"nested":{"api_key":"fake-secret"},"message":"Bearer abcdefg","keep":42}'
        result = json.loads(sanitized(raw))
        self.assertEqual(result, {"nested": {"api_key": "[REDACTED]"}, "message": "[REDACTED]", "keep": 42})
        lines = b'{"password":"secret"}\n{"keep":"event"}\n'
        self.assertEqual([json.loads(line) for line in sanitized(lines).splitlines()],
                         [{"password": "[REDACTED]"}, {"keep": "event"}])
        self.assertNotIn(b"PRIVATE KEY", sanitized(
            b"-----BEGIN OPENSSH PRIVATE KEY-----\nsecret\n-----END OPENSSH PRIVATE KEY-----"))

    def test_signed_object_download_never_receives_solver_authorization(self):
        client = RemoteClient(self.root / "client", bearer="alice-token")
        client.base = "https://service.invalid"
        identity = self.create()
        descriptor = {"sha256": "a" * 64, "bytes": 10, "media_type": "application/zip",
                      "url": "https://bucket.s3.amazonaws.com/key?signature=temporary"}
        with patch.object(client, "artifacts", return_value={"artifacts": {"complete": descriptor}}), \
                patch("catalyst.remote.solver_fetch", return_value=json.dumps(descriptor).encode()), \
                patch("catalyst.remote.fetch") as get:
            client.download_artifact(identity, "complete", self.root / "out.zip")
            self.assertEqual(get.call_args.args, (descriptor["url"], ""))

    def test_download_checksum_failure_does_not_replace_existing_file(self):
        output = self.root / "out.zip"
        output.write_bytes(b"previous")
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=None)
        response.read.side_effect = [b"wrong", b""]
        with patch("catalyst.remote.urllib.request.build_opener") as opener:
            opener.return_value.open.return_value = response
            with self.assertRaisesRegex(CatalystError, "checksum"):
                fetch("https://objects.invalid/file", "", output=output, limit=10,
                      expected_size=5, expected_sha256="0" * 64)
        self.assertEqual(output.read_bytes(), b"previous")
        self.assertFalse(list(self.root.glob(".artifact-*")))


class StorageTests(unittest.TestCase):
    def test_existing_s3_object_and_mismatched_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_json(root / "artifact-storage.json", {
                "backend": "s3", "bucket": "example-artifacts", "region": "us-west-2",
            })
            source = root / "file.zip"
            source.write_bytes(b"fixture")
            client = Mock()
            failure = RuntimeError("existing")
            failure.response = {"ResponseMetadata": {"HTTPStatusCode": 412}}
            client.put_object.side_effect = failure
            sha = hashlib.sha256(b"fixture").hexdigest()
            client.head_object.return_value = {"ContentLength": 7, "Metadata": {"sha256": sha}}
            self.assertEqual(ArtifactStorage(root, client=client).put(source)["sha256"], sha)
            client.head_object.return_value = {"ContentLength": 8, "Metadata": {"sha256": sha}}
            with self.assertRaisesRegex(CatalystError, "does not match"):
                ArtifactStorage(root, client=client).put(source)

    def test_s3_private_encrypted_conditional_put_and_scoped_presign(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_json(root / "artifact-storage.json", {
                "backend": "s3", "bucket": "example-artifacts", "region": "us-west-2",
            })
            source = root / "file.zip"
            source.write_bytes(b"fixture")
            client = Mock()
            storage = ArtifactStorage(root, client=client)
            item = storage.put(source)
            arguments = client.put_object.call_args.kwargs
            self.assertEqual(arguments["ServerSideEncryption"], "AES256")
            self.assertEqual(arguments["IfNoneMatch"], "*")
            self.assertNotIn("ACL", arguments)
            self.assertEqual(arguments["Key"], f"catalyst/sha256/{item['sha256']}.zip")
            storage.download_url(item)
            self.assertEqual(client.generate_presigned_url.call_args.kwargs["ExpiresIn"], 300)
            item["storage"]["bucket"] = "different-bucket"
            with self.assertRaises(CatalystError):
                storage.download_url(item)


if __name__ == "__main__":
    unittest.main()
