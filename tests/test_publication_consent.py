import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from catalyst.cli import build_parser, remote_command
from catalyst.common import CatalystError
from catalyst.publication import publication_choices
from catalyst.remote import request_body
from harness_fixture import create_harness


class PublicationConsentTests(unittest.TestCase):
    def test_source_is_public_by_default_but_no_license_or_traces_are_granted(self):
        self.assertEqual(publication_choices(), {"harness": True, "traces": False, "license": None})
        parser, _ = build_parser()
        args = parser.parse_args(["remote", "submit", "harness"])
        self.assertFalse(args.private_harness)
        self.assertIsNone(args.source_license)

    def test_submission_request_carries_public_default_without_a_publish_command(self):
        with tempfile.TemporaryDirectory() as temporary:
            harness = Path(temporary) / "harness"
            create_harness(harness)
            body = request_body(harness, "https://verifier.example.test")
            self.assertEqual(body["publication"], {
                "harness": True, "traces": False, "license": None})

    def test_private_source_is_supported_and_trace_review_cannot_be_skipped(self):
        self.assertEqual(publication_choices({"harness": False, "traces": False, "license": None}),
                         {"harness": False, "traces": False, "license": None})
        for choices in (
            {"harness": True, "traces": True, "license": "MIT"},
            {"harness": False, "traces": False, "license": "MIT"},
            {"harness": True, "traces": False, "license": "unknown"},
            {"harness": "true", "traces": False, "license": None},
        ):
            with self.subTest(choices=choices), self.assertRaises(CatalystError):
                publication_choices(choices)

    def test_source_review_required_before_publication_request(self):
        parser, _ = build_parser()
        args = parser.parse_args(["remote", "publish", "example", "--harness", "--license", "MIT"])
        with patch("catalyst.remote.RemoteClient") as factory:
            with self.assertRaisesRegex(CatalystError, "confirm-source-reviewed"):
                remote_command(args, Path("."))
            factory.return_value.sharing.assert_not_called()

    def test_reviewed_source_does_not_publish_traces(self):
        parser, _ = build_parser()
        args = parser.parse_args([
            "remote", "publish", "example", "--harness", "--license", "MIT", "--confirm-source-reviewed",
        ])
        with patch("catalyst.remote.RemoteClient") as factory, contextlib.redirect_stdout(io.StringIO()):
            factory.return_value.sharing.return_value = {}
            remote_command(args, Path("."))
            factory.return_value.sharing.assert_called_once_with("example", {"harness": True, "license": "MIT"})
