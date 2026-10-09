"""The helper resumes binding after an uncertain response without re-submitting."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

from catalyst.common import CatalystError, read_json, write_json
from catalyst.yukon_submit import submit


class YukonSubmitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.job, self.benchmark, self.submission = (str(uuid.uuid4()) for _ in range(3))
        self.reference = {"evaluation_id": str(uuid.uuid4())}
        write_json(self.root / "benchmark.json", {"editablePaths": ["submission/verification.json"]})
        write_json(self.root / "submission/verification.json", self.reference)
        self.note = self.root / "note.md"
        self.note.write_text("Reviewed public note.")
        self.response = {
            "job": {"id": self.job, "benchmarkId": self.benchmark, "submissionId": self.submission},
            "submission": {"id": self.submission, "benchmarkId": self.benchmark},
        }
        self.result = {"job_id": self.job, "benchmark_id": self.benchmark,
                       "submission_id": self.submission}

    def invoke(self):
        return submit(self.root, note_file=self.note, model="GPT 6 Astra",
                      harness="Codex", no_dependencies=True)

    def test_binding_failure_resumes_same_submission_without_another_yukon_upload(self):
        with patch("catalyst.yukon_submit.endpoint", return_value="https://verifier.example"), \
                patch("catalyst.yukon_submit.check_receipt") as preview, \
                patch("catalyst.yukon_submit.subprocess.run",
                      return_value=SimpleNamespace(returncode=0, stdout=json.dumps(self.response))) as run, \
                patch("catalyst.yukon_submit.bind_job",
                      side_effect=[CatalystError("temporarily unavailable"), self.result]) as bind:
            with self.assertRaisesRegex(CatalystError, "temporarily unavailable"):
                self.invoke()
            pending = read_json(self.root / ".catalyst/yukon/pending-submission.json")
            self.assertEqual(pending["phase"], "binding")
            self.assertEqual(pending["job_id"], self.job)
            self.assertEqual(self.invoke(), self.result)
            run.assert_called_once()
            preview.assert_called_once()
            self.assertEqual(bind.call_args_list[0], bind.call_args_list[1])
            self.assertFalse((self.root / ".catalyst/yukon/pending-submission.json").exists())

    def test_unknown_submit_outcome_blocks_duplicate_upload(self):
        with patch("catalyst.yukon_submit.endpoint", return_value="https://verifier.example"), \
                patch("catalyst.yukon_submit.check_receipt"), \
                patch("catalyst.yukon_submit.subprocess.run",
                      return_value=SimpleNamespace(returncode=1, stdout="")) as run:
            with self.assertRaises(CatalystError):
                self.invoke()
            with self.assertRaisesRegex(CatalystError, "previous Yukon submission outcome is unknown"):
                self.invoke()
            run.assert_called_once()

    def test_pending_binding_cannot_switch_receipt(self):
        write_json(self.root / ".catalyst/yukon/pending-submission.json",
                   {"phase": "binding", "endpoint": "https://verifier.example",
                    "reference": {"evaluation_id": str(uuid.uuid4())}})
        with patch("catalyst.yukon_submit.endpoint", return_value="https://verifier.example"), \
                patch("catalyst.yukon_submit.bind_job") as bind:
            with self.assertRaisesRegex(CatalystError, "Restore the pending submission"):
                self.invoke()
            bind.assert_not_called()
