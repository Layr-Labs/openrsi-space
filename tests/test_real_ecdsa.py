"""Real-problem service bindings and capture safety; full Rust grading is an integration run."""
import copy
from decimal import Decimal
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import uuid
import zipfile

from catalyst.common import CatalystError, digest_files
from catalyst.evaluator import APIError, validate_request
from catalyst.local_run import MockProvider
from catalyst.problems import initial_problems
from catalyst.remote import judgment, request_body
from catalyst.worker import archive_traces, candidate_files, capture_candidate, DungenessLocalBackend
from test_yukon import completed

PROJECT = Path(__file__).resolve().parents[1]


class RealECDSATests(unittest.TestCase):
    def body(self):
        with patch.dict(os.environ, {"CATALYST_LOCAL_ECDSA": "1", "CATALYST_LOCAL_TEST": ""}):
            return request_body(PROJECT / "harnesses/ecdsa-baseline", "http://127.0.0.1:8778")

    def test_real_mode_uses_the_official_pin_and_is_not_a_fixture_or_hosted_result(self):
        body = self.body()
        self.assertEqual(body["evidence_mode"], "local-ecdsa")
        self.assertEqual(body["problem_set"], initial_problems())
        request = {**body, "request_id": str(uuid.uuid4())}
        validate_request(request, initial_problems(), evidence_mode="local-ecdsa")
        with self.assertRaises(APIError):
            validate_request(request, initial_problems())
        forged = copy.deepcopy(request)
        forged["problem_set"][0]["repository"]["commit"] = "a" * 40
        with self.assertRaises(APIError):
            validate_request(forged, initial_problems(), evidence_mode="local-ecdsa")
        result = completed(request, str(uuid.uuid4()))
        for mode in ("remote", "local-test"):
            with self.assertRaisesRegex(CatalystError, "cannot be used"):
                judgment(result, {**request, "evidence_mode": mode})

    def test_local_modes_are_exclusive_and_loopback_only(self):
        with patch.dict(os.environ, {"CATALYST_LOCAL_ECDSA": "1", "CATALYST_LOCAL_TEST": "1"}):
            with self.assertRaisesRegex(CatalystError, "not both"):
                request_body(PROJECT / "harnesses/ecdsa-baseline", "http://127.0.0.1:8778")
        with patch.dict(os.environ, {"CATALYST_LOCAL_ECDSA": "1", "CATALYST_LOCAL_TEST": ""}):
            with self.assertRaisesRegex(CatalystError, "loopback"):
                request_body(PROJECT / "harnesses/ecdsa-baseline", "https://remote.invalid")

    def test_model_disabled_backend_cannot_return_a_mock_completion_or_charge(self):
        evaluation = self.body()["evaluation"]
        with MockProvider(evaluation, allow_model_calls=False) as provider:
            request = Request(
                f"http://127.0.0.1:{provider.server.server_port}/v1/chat/completions",
                data=json.dumps({"model": evaluation["model"]["name"]}).encode(),
                headers={"Authorization": "Bearer " + provider.key, "Content-Type": "application/json"})
            with self.assertRaises(HTTPError) as error:
                urlopen(request)
            self.assertEqual(error.exception.code, 403)
            error.exception.close()
            self.assertEqual(provider.attempts, 1)
            self.assertEqual(provider.receipts, [])
            self.assertEqual(provider.total, Decimal(0))
        with self.assertRaisesRegex(CatalystError, "disabled"):
            DungenessLocalBackend({"mode": "local-ecdsa", "model_access": "metered"})

    def test_directory_capture_is_frozen_hashed_and_in_private_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "mod.rs").write_text("pub fn build() {}\n")
            (source / "arithmetic").mkdir()
            (source / "arithmetic/add.rs").write_text("// arithmetic\n")
            artifacts = root / "artifacts"
            digest = capture_candidate(source, artifacts / "candidate", "src/point_add")
            captured = artifacts / "candidate/src/point_add"
            self.assertEqual(digest, digest_files(candidate_files(captured, "src/point_add")))
            (source / "mod.rs").write_text("changed source\n")
            self.assertEqual(digest, digest_files(candidate_files(captured, "src/point_add")))
            self.assertEqual((captured / "mod.rs").stat().st_mode & 0o777, 0o444)
            archive_traces(artifacts)
            with zipfile.ZipFile(artifacts / "traces.zip") as archive:
                self.assertIn("candidate/src/point_add/mod.rs", archive.namelist())
                self.assertIn("candidate/src/point_add/arithmetic/add.rs", archive.namelist())

    def test_capture_rejects_links_special_files_and_oversized_modules(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "mod.rs").symlink_to(root / "missing")
            with self.assertRaisesRegex(CatalystError, "symlinks"):
                candidate_files(source, "src/point_add")
            (source / "mod.rs").unlink()
            os.mkfifo(source / "pipe")
            with self.assertRaisesRegex(CatalystError, "non-regular"):
                candidate_files(source, "src/point_add")
            (source / "pipe").unlink()
            (source / "large.rs").write_bytes(b"x" * (8 * 1024 * 1024 + 1))
            with self.assertRaisesRegex(CatalystError, "8 MiB"):
                candidate_files(source, "src/point_add")
