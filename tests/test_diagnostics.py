from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from openrsi_space.cli import build_parser, remote_command
from openrsi_space.client.evaluations import RemoteClient
from openrsi_space.common import OpenRSIError
from openrsi_space.progress import diagnostic_lines, progress_line


IDENTITY = "a21c947a-b361-4710-ba4c-74ebc47afa96"


def report():
    return {"protocol": "catalyst-diagnostics-v1", "evaluation_id": IDENTITY,
            "scoring_evidence": False,
            "runtime": {"code": "HARNESS_EXIT_NONZERO", "reported": {
                "exception_type": "FileExistsError", "message": "secret\x1b[31m"}},
            "verification": {"code": "CANDIDATE_REJECTED"},
            "evaluations": {"events": [{"code": "CANDIDATE_REJECTED"}]}}


class DiagnosticsTests(unittest.TestCase):
    def client(self, root):
        client = object.__new__(RemoteClient)
        client.state = Path(root)
        client.base = "https://verifier.example.test"
        client.bearer = "synthetic-owner-token"
        return client

    def test_read_diagnostics_without_session_or_submission_and_save_privately(self):
        with tempfile.TemporaryDirectory() as root:
            client = self.client(root)
            output = Path(root) / "report.json"
            Path(root).chmod(0o755)
            output.write_text("old")
            output.chmod(0o644)
            with patch("openrsi_space.client.transport.solver_fetch", return_value=json.dumps(report())) as fetch:
                self.assertEqual(client.diagnostics(IDENTITY, output), report())
            fetch.assert_called_once_with(client.base, f"/evaluations/{IDENTITY}/diagnostics", client.bearer)
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertEqual(Path(root).stat().st_mode & 0o777, 0o755)
            self.assertEqual(json.loads(output.read_text()), report())
            self.assertFalse((Path(root) / "remote").exists())

    def test_reject_mismatched_reports_before_writing(self):
        with tempfile.TemporaryDirectory() as root:
            client = self.client(root)
            output = Path(root) / "report.json"
            for change in ({"protocol": "unknown"}, {"evaluation_id": "other"},
                           {"scoring_evidence": True}, {"scoring_evidence": 0}):
                with self.subTest(change=change), patch("openrsi_space.client.transport.solver_fetch",
                        return_value=json.dumps({**report(), **change})):
                    with self.assertRaises(OpenRSIError):
                        client.diagnostics(IDENTITY, output)
                self.assertFalse(output.exists())
            with patch("openrsi_space.client.transport.solver_fetch") as fetch:
                with self.assertRaises(OpenRSIError):
                    client.diagnostics("../another-owner")
                fetch.assert_not_called()

    def test_cli_diagnostics_emits_json_and_never_submits(self):
        parser, _ = build_parser()
        args = parser.parse_args(["remote", "diagnostics", IDENTITY, "--output", "report.json"])
        out = io.StringIO()
        with patch("openrsi_space.client.evaluations.RemoteClient") as factory, redirect_stdout(out):
            factory.return_value.diagnostics.return_value = report()
            remote_command(args, Path("."))
            factory.return_value.diagnostics.assert_called_once_with(IDENTITY, "report.json")
            factory.return_value.submit.assert_not_called()
        self.assertEqual(json.loads(out.getvalue()), report())

    def test_render_only_fixed_messages_and_known_exception_types(self):
        result = {"status": "running", "diagnostics": report(), "progress": {"schema_version": 1}}
        lines = "\n".join(diagnostic_lines(result))
        self.assertIn("Harness-reported exception: FileExistsError", lines)
        self.assertIn(f"remote diagnostics {IDENTITY}", lines)
        self.assertIn("latest evaluation: CANDIDATE_REJECTED", progress_line(result))
        self.assertNotIn("secret", lines)
        self.assertNotIn("\x1b", lines)
        for bad in ([], {}, "secret\x1b[31m", None):
            result["diagnostics"]["runtime"] = {"code": bad, "reported": {"exception_type": bad}}
            result["diagnostics"]["verification"] = {"code": bad}
            result["diagnostics"]["evaluations"]["events"] = [{"code": bad}]
            self.assertEqual(diagnostic_lines(result), [])
            self.assertNotIn("latest evaluation", progress_line(result))
        result["diagnostics"] = {**report(), "evaluation_id": "x; echo secret"}
        self.assertNotIn("remote diagnostics", "\n".join(diagnostic_lines(result)))

    def test_wait_reports_failed_and_completed_invalid_runs_on_stderr(self):
        for status in ("failed", "completed"):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as root:
                client = self.client(root)
                result = {"status": status, "diagnostics": report(), "valid": False}
                errors, out = io.StringIO(), io.StringIO()
                with patch.object(client, "session", return_value={"request": {}}), \
                        patch.object(client, "status", return_value=result), \
                        patch.object(client, "clear_pending"), \
                        patch("openrsi_space.client.evaluations.judgment", return_value={"valid": False}) as judge, \
                        patch("openrsi_space.client.evaluations.verification_reference", return_value={}), \
                        redirect_stderr(errors), redirect_stdout(out):
                    if status == "failed":
                        with self.assertRaises(OpenRSIError):
                            client.wait(IDENTITY)
                        judge.assert_not_called()
                    else:
                        self.assertEqual(client.wait(IDENTITY), {"valid": False})
                        judge.assert_called_once_with(result, {})
                self.assertEqual(out.getvalue(), "")
                self.assertIn("HARNESS_EXIT_NONZERO", errors.getvalue())
                self.assertIn("CANDIDATE_REJECTED", errors.getvalue())
                self.assertNotIn("secret", errors.getvalue())

    def test_missing_usage_explanation_is_safe_and_distinct_from_harness_failure(self):
        doc=report()
        doc['worker']={'code':'MODEL_USAGE_UNAVAILABLE'}
        doc['model_failures']={'events':[{'code':'MODEL_USAGE_UNAVAILABLE',
            'category':'upstream_protocol_error','request_status':'stream_interrupted','error':'secret\x1b'}]}
        lines='\n'.join(diagnostic_lines({'diagnostics':doc}))
        self.assertIn('upstream HTTP protocol failure',lines)
        self.assertIn('Later requests do not settle',lines)
        self.assertIn('HARNESS_EXIT_NONZERO',lines)
        self.assertEqual(lines.count('MODEL_USAGE_UNAVAILABLE:'),1)
        self.assertNotIn('secret',lines)
