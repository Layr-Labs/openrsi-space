from contextlib import redirect_stderr
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from catalyst.common import CatalystError
from catalyst.progress import progress_line, diagnostic_lines
from catalyst.remote import RemoteClient


class ProgressTests(unittest.TestCase):
    def test_unsettled_amount_is_not_displayed_as_complete_or_free(self):
        result = {'status':'running', 'progress':{'schema_version':1,
                  'usage':{'normalized_model_credits':0, 'accounting_state':'incomplete'}}}
        self.assertIn('settled; total unknown (missing usage)', progress_line(result))
        result['progress']['usage']['accounting_state'] = 'pending'
        self.assertIn('settled; model request pending', progress_line(result))

    def test_progress_is_useful_and_provisional_without_raw_remote_text(self):
        result = {"status": "running", "progress": {
            "schema_version": 1, "elapsed_seconds": 487, "max_model_credits": 3,
            "usage": {"normalized_model_credits": 1.807234, "model_requests": 25},
            "evaluation": {"completed": 4, "best_performance": 10704574395},
            "snapshot_age_seconds": 45, "message": "secret\x1b[31m",
        }}
        line = progress_line(result)
        for text in ("elapsed 8m 07s", "model budget: $1.807234 / $3", "25 model requests",
                     "4 evaluations", "best 10,704,574,395 (provisional)", "last metrics 0m 45s ago"):
            self.assertIn(text, line)
        self.assertNotIn("secret", line)
        self.assertNotIn("\x1b", line)

    def test_setup_phases_use_fixed_labels_and_do_not_imply_inference_started(self):
        result = {'status':'building','progress':{'schema_version':1,'phase':'image_review',
                  'phase_elapsed_seconds':67,'usage':None}}
        line = progress_line(result)
        self.assertIn('reviewing built image',line)
        self.assertIn('phase 1m 07s',line)
        self.assertIn('research model calls not started',line)
        result['progress']['phase'] = 'private\x1b[31m'
        self.assertNotIn('private',progress_line(result))
        result['progress']['phase'] = []
        self.assertNotIn('reviewing',progress_line(result))

    def test_terminal_completion_distinguishes_score_and_actual_billing(self):
        result = {'status':'completed','valid':False,
                  'provider_billing':{'complete':True,'total_usd':0.159655}}
        line = progress_line(result,600)
        self.assertIn('no verified score',line)
        self.assertIn('provider billed $0.159655',line)
        self.assertNotIn('waiting',line)
        result['valid'] = True
        self.assertIn('verified result',progress_line(result))
        result['provider_billing'] = {'complete':False,'total_usd':0}
        self.assertIn('total unknown',progress_line(result))
        self.assertNotIn('billed $0',progress_line(result))

    def test_request_reservation_is_explained_without_echoing_remote_strings(self):
        event = {'code':'MODEL_RESERVATION_EXCEEDS_REMAINING_BUDGET',
                 'available_usd':0.840345,'required_reservation_usd':0.99545,
                 'upstream_request_sent':False,'message':'private\x1b[31m'}
        result = {'diagnostics':{'protocol':'catalyst-diagnostics-v1','model_failures':{'events':[event]}}}
        text = '\n'.join(diagnostic_lines(result))
        for value in ('$0.840345','$0.995450','no model charge','output-token limit'):
            self.assertIn(value,text)
        self.assertNotIn('private',text)
        event.update(available_usd=float('nan'),required_reservation_usd='private')
        self.assertNotIn('nan','\n'.join(diagnostic_lines(result)))

    def test_missing_and_invalid_metrics_are_not_zero_scores_or_terminal_text(self):
        self.assertIn("no live metrics available", progress_line({"status": "running"}, 31))
        line = progress_line({"status": "running", "progress": {
            "schema_version": 1, "usage": {"normalized_model_credits": float("nan"),
                                        "model_requests": "secret\x1b[0m"},
            "evaluation": {"best_performance": None, "completed": -1},
        }})
        self.assertNotIn("best", line)
        self.assertNotIn("credits", line)
        self.assertNotIn("secret", line)
        zero = progress_line({"status": "running", "progress": {
            "schema_version": 1, "evaluation": {"best_performance": 0},
        }})
        self.assertIn("best 0 (provisional)", zero)

    def test_wait_keeps_json_stdout_clean_and_reports_heartbeat_and_phase_change(self):
        with tempfile.TemporaryDirectory() as root:
            client = object.__new__(RemoteClient)
            client.state = Path(root)
            states = [{"status": "running"}, {"status": "running"}, {"status": "running"},
                      {"status": "verifying"}, {"status": "failed", "reason": "contract fixture"}]
            errors = io.StringIO()
            with patch.object(client, "session", return_value={"request": {}}), \
                    patch.object(client, "clear_pending"), patch.object(client, "status", side_effect=states), \
                    patch("catalyst.remote.time.monotonic", side_effect=[0, 0, 5, 15, 16, 17]), \
                    patch("catalyst.remote.time.sleep"), redirect_stderr(errors):
                with self.assertRaises(CatalystError):
                    client.wait("a21c947a-b361-4710-ba4c-74ebc47afa96")
            lines = errors.getvalue().splitlines()
            self.assertEqual(len(lines), 4)
            self.assertIn("no live metrics available", lines[1])
            self.assertIn("verifying", lines[2])
