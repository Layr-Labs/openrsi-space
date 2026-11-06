import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from openrsi_space.cli import build_parser, remote_command
from openrsi_space.common import OpenRSIError
from openrsi_space.publication import publication_choices
from openrsi_space.remote import request_body
from harness_fixture import create_harness


class PublicationConsentTests(unittest.TestCase):
    def test_run_visibility_notice_precedes_submission_even_without_interactive_input(self):
        parser, _ = build_parser()
        for flags in ([], ["--platform-funded"]):
            with self.subTest(flags=flags):
                args = parser.parse_args(["remote", "submit", "harness", *flags])
                errors, output = io.StringIO(), io.StringIO()

                def stop_before_preflight(*_args, **_kwargs):
                    self.assertIn(
                        "Every remote run, including unsuccessful runs, is listed publicly under your username.",
                        errors.getvalue(),
                    )
                    self.assertIn("publication screening passes", errors.getvalue())
                    self.assertIn("Traces are retained internally.", errors.getvalue())
                    raise OpenRSIError("stop before preflight")

                with patch("openrsi_space.remote.RemoteClient") as factory, \
                        patch("openrsi_space.client.configuration.evaluation_config", side_effect=stop_before_preflight), \
                        patch("openrsi_space.cli.model_access_input") as credential, \
                        patch("sys.stdin", io.StringIO()), \
                        contextlib.redirect_stderr(errors), contextlib.redirect_stdout(output):
                    with self.assertRaisesRegex(OpenRSIError, "stop before preflight"):
                        remote_command(args, Path("."))
                    factory.return_value.submit.assert_not_called()
                    credential.assert_not_called()
                self.assertEqual(output.getvalue(), "")

    def test_source_is_public_by_default_but_no_license_or_traces_are_granted(self):
        self.assertEqual(publication_choices(), {"harness": True, "traces": False, "license": None})
        parser, _ = build_parser()
        args = parser.parse_args(["remote", "submit", "harness"])
        self.assertFalse(hasattr(args, "private_harness"))
        self.assertIsNone(args.source_license)

    def test_submission_request_carries_public_default_without_a_publish_command(self):
        with tempfile.TemporaryDirectory() as temporary:
            harness = Path(temporary) / "harness"
            create_harness(harness)
            body = request_body(harness, "https://verifier.example.test")
            self.assertEqual(body["publication"], {
                "harness": True, "traces": False, "license": None})

    def test_historical_private_source_remains_readable_and_trace_publication_is_disabled(self):
        self.assertEqual(publication_choices({"harness": False, "traces": False, "license": None}),
                         {"harness": False, "traces": False, "license": None})
        for choices in (
            {"harness": True, "traces": True, "license": "MIT"},
            {"harness": False, "traces": False, "license": "MIT"},
            {"harness": True, "traces": False, "license": "unknown"},
            {"harness": "true", "traces": False, "license": None},
        ):
            with self.subTest(choices=choices), self.assertRaises(OpenRSIError):
                publication_choices(choices)

    def test_private_submission_is_rejected_before_reading_source_or_credentials(self):
        with self.assertRaisesRegex(OpenRSIError, "must be public"):
            request_body(Path("missing-harness"), "https://verifier.example.test",
                         publication={"harness": False, "traces": False, "license": None})

    def test_cli_has_no_private_submission_or_unpublish_option(self):
        parser, _ = build_parser()
        for arguments in (["remote", "submit", "harness", "--private-harness"],
                          ["remote", "unpublish", "example", "--harness"]):
            with self.subTest(arguments=arguments), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    parser.parse_args(arguments)
                self.assertEqual(raised.exception.code, 2)

    def test_source_review_required_before_publication_request(self):
        parser, _ = build_parser()
        args = parser.parse_args(["remote", "publish", "example", "--harness", "--license", "MIT"])
        with patch("openrsi_space.remote.RemoteClient") as factory:
            with self.assertRaisesRegex(OpenRSIError, "confirm-source-reviewed"):
                remote_command(args, Path("."))
            factory.return_value.sharing.assert_not_called()

    def test_reviewed_source_does_not_publish_traces(self):
        parser, _ = build_parser()
        args = parser.parse_args([
            "remote", "publish", "example", "--harness", "--license", "MIT", "--confirm-source-reviewed",
        ])
        with patch("openrsi_space.remote.RemoteClient") as factory, contextlib.redirect_stdout(io.StringIO()):
            factory.return_value.sharing.return_value = {}
            remote_command(args, Path("."))
            factory.return_value.sharing.assert_called_once_with("example", {"harness": True, "license": "MIT"})

    def test_reviewed_source_can_be_public_without_granting_a_license(self):
        parser, _ = build_parser()
        args = parser.parse_args(["remote", "publish", "example", "--harness", "--confirm-source-reviewed"])
        with patch("openrsi_space.remote.RemoteClient") as factory, contextlib.redirect_stdout(io.StringIO()):
            factory.return_value.sharing.return_value = {}
            remote_command(args, Path("."))
            factory.return_value.sharing.assert_called_once_with("example", {"harness": True})
