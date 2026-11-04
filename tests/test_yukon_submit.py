"""The helper resumes binding after an uncertain response without re-submitting."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

from openrsi_space.common import OpenRSIError, read_json, write_json
from openrsi_space.yukon_submit import submit


class YukonSubmitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.job, self.benchmark, self.submission = (str(uuid.uuid4()) for _ in range(3))
        self.enterContext(patch("openrsi_space.yukon_submit.local_benchmark", return_value=self.benchmark))
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
        with patch("openrsi_space.yukon_submit.endpoint", return_value="https://verifier.example"), \
                patch("openrsi_space.yukon_submit.check_receipt") as preview, \
                patch("openrsi_space.yukon_submit.subprocess.run",
                      return_value=SimpleNamespace(returncode=0, stdout=json.dumps(self.response))) as run, \
                patch("openrsi_space.yukon_submit.bind_job",
                      side_effect=[OpenRSIError("temporarily unavailable"), self.result]) as bind:
            with self.assertRaisesRegex(OpenRSIError, "temporarily unavailable"):
                self.invoke()
            pending = read_json(self.root / ".openrsi/yukon/pending-submission.json")
            self.assertEqual(pending["phase"], "binding")
            self.assertEqual(pending["job_id"], self.job)
            self.assertEqual(self.invoke(), self.result)
            run.assert_called_once()
            preview.assert_called_once()
            self.assertEqual(bind.call_args_list[0], bind.call_args_list[1])
            self.assertFalse((self.root / ".openrsi/yukon/pending-submission.json").exists())

    def test_unknown_submit_outcome_blocks_duplicate_upload(self):
        with patch("openrsi_space.yukon_submit.endpoint", return_value="https://verifier.example"), \
                patch("openrsi_space.yukon_submit.check_receipt"), \
                patch("openrsi_space.yukon_submit.subprocess.run",
                      return_value=SimpleNamespace(returncode=1, stdout="")) as run:
            with self.assertRaises(OpenRSIError):
                self.invoke()
            with self.assertRaisesRegex(OpenRSIError, "previous Yukon submission outcome is unknown"):
                self.invoke()
            run.assert_called_once()

    def test_pending_binding_cannot_switch_receipt(self):
        write_json(self.root / ".openrsi/yukon/pending-submission.json",
                   {"phase": "binding", "endpoint": "https://verifier.example",
                    "reference": {"evaluation_id": str(uuid.uuid4())}})
        with patch("openrsi_space.yukon_submit.endpoint", return_value="https://verifier.example"), \
                patch("openrsi_space.yukon_submit.bind_job") as bind:
            with self.assertRaisesRegex(OpenRSIError, "Restore the pending submission"):
                self.invoke()
            bind.assert_not_called()


    def test_legacy_board_fails_before_receipt_read_or_submission_and_keeps_files(self):
        with patch("openrsi_space.yukon_submit.local_benchmark", return_value="8d3a2daa-afab-4685-b93a-7443c83049d2"), \
                patch("openrsi_space.yukon_submit.check_receipt") as receipt, \
                patch("openrsi_space.yukon_submit.subprocess.run") as network:
            with self.assertRaisesRegex(OpenRSIError, "yukon clone bxue-l2/openrsi-space"):
                self.invoke()
            receipt.assert_not_called()
            network.assert_not_called()
        self.assertEqual(read_json(self.root / "submission/verification.json"), self.reference)
        self.assertFalse((self.root / ".openrsi/yukon/pending-submission.json").exists())

    def test_legacy_pending_binding_is_preserved_and_not_retried(self):
        pending = self.root / ".openrsi/yukon/pending-submission.json"
        saved = {"phase": "binding", "benchmark_id": "8d3a2daa-afab-4685-b93a-7443c83049d2"}
        write_json(pending, saved)
        with patch("openrsi_space.yukon_submit.bind_job") as bind:
            with self.assertRaisesRegex(OpenRSIError, "No new local or paid remote run"):
                self.invoke()
            bind.assert_not_called()
        self.assertEqual(read_json(pending), saved)

    def test_returned_board_mismatch_preserves_job_without_binding_or_reupload(self):
        wrong = str(uuid.uuid4())
        self.response['job']['benchmarkId'] = wrong
        self.response['submission']['benchmarkId'] = wrong
        with patch('openrsi_space.yukon_submit.endpoint', return_value='https://verifier.example'), \
                patch('openrsi_space.yukon_submit.check_receipt'), \
                patch('openrsi_space.yukon_submit.subprocess.run', return_value=SimpleNamespace(
                    returncode=0, stdout=json.dumps(self.response))) as run, \
                patch('openrsi_space.yukon_submit.bind_job') as bind:
            for _ in range(2):
                with self.assertRaisesRegex(OpenRSIError, 'different benchmark'):
                    self.invoke()
            run.assert_called_once()
            bind.assert_not_called()
        pending = read_json(self.root/'.openrsi/yukon/pending-submission.json')
        self.assertEqual(pending['benchmark_id'], wrong)
        self.assertEqual(pending['job_id'], self.job)
