import contextlib
import io
from pathlib import Path
import unittest
from unittest.mock import patch

from catalyst.cli import build_parser, remote_command
from catalyst.common import CatalystError


class PublicationConsentTests(unittest.TestCase):
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
