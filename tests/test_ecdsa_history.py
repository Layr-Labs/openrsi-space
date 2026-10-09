"""Existing Dungeness event contracts; no model requests or new capture format."""
import json
from pathlib import Path
import tempfile
import unittest

from catalyst.common import CatalystError
from catalyst.ecdsa_history import project_history
from catalyst.tiers import pricing_digest, project_observation
from test_tiers import MODEL, LIMITS, candidate, usage


def charge(seq, request, cost):
    return {"sequence": seq, "source": "gateway", "kind": "model.accounting",
            "request_id": request, "data": {"normalized_usd": cost}}


def evaluation(seq, cost, performance):
    return {"sequence": seq, "source": "evaluator", "kind": "evaluation.completed",
            "usage": {"normalized_usd": cost}, "data": {
                "operation": "score", "status": "ok", "candidate_sha256": "a" * 64,
                "source_sha256": "b" * 64, "avg_toffoli": performance / 10,
                "peak_qubits": 10, "score": performance}}


class EcdsaHistoryTests(unittest.TestCase):
    def project(self, events, ledger, final=(), total=25, cap=30):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "usage").mkdir()
            (root / "usage/events.jsonl").write_text("\n".join(map(json.dumps, events)) + "\n")
            settled, curve, end, omitted = project_history(root, ledger, final, MODEL)
        result = project_observation({
            "pricing_digest": pricing_digest(), "end_sequence": end,
            "usage": settled, "curve": curve, "normalized_model_usd": total,
        }, MODEL, cap, LIMITS)
        return result, omitted

    def test_retains_early_improvement_regression_and_final_result(self):
        events = [charge(2, "call-1", 19), evaluation(4, 19, 100),
                  charge(8, "call-2", 6), evaluation(9, 25, 80), evaluation(10, 25, 90)]
        result, _ = self.project(events, [usage(1, 19), usage(2, 6)], [candidate(1, 25, 90)])
        self.assertEqual([p["performance"] for p in result["curve"]], [100, 80, 90, 90])
        self.assertEqual([t["best"]["performance"] for t in result["tiers"]], [100, 80])
        self.assertEqual(result["best"]["verification_source"], "dungeness-evaluator")
        self.assertEqual(result["best"]["gateway_sequence"], 9)
        self.assertEqual(result["curve"][-1]["verification_source"], "terminal-verifier")

    def test_streaming_usage_cannot_understate_a_budget_view(self):
        events = [charge(1, "call-1", 19), evaluation(2, 19, 100),
                  {"sequence": 3, "source": "gateway", "kind": "model.request", "request_id": "call-2"},
                  evaluation(4, 19, 50), charge(5, "call-2", 6)]
        result, _ = self.project(events, [usage(1, 19), usage(2, 6)])
        self.assertEqual([p["normalized_model_usd"] for p in result["curve"]], [19, 25])
        self.assertEqual(result["tiers"][0]["best"]["performance"], 100)

    def test_failed_and_unordered_evaluations_cannot_be_promoted(self):
        invalid = evaluation(2, 5, 1)
        invalid["data"]["status"] = "invalid"
        fallback = evaluation(None, 5, 1)
        result, omitted = self.project([charge(1, "call-1", 5), invalid, fallback],
                                      [usage(1, 5)], [candidate(3, 5, 100)], total=5, cap=5)
        self.assertEqual(len(result["curve"]), 1)
        self.assertEqual(omitted, 1)
        self.assertEqual([t["status"] for t in result["tiers"]], ["eligible", "eligible"])

    def test_tampered_snapshots_digest_or_score_fail_closed(self):
        for field, value in (("candidate_sha256", "bad"), ("source_sha256", None),
                             ("score", 1), ("peak_qubits", True)):
            point = evaluation(2, 25, 100)
            point["data"][field] = value
            with self.subTest(field=field), self.assertRaises(CatalystError):
                self.project([charge(1, "call-1", 25), point], [usage(1, 25)])
        with self.assertRaisesRegex(CatalystError, "snapshot"):
            self.project([charge(1, "call-1", 25), evaluation(2, 20, 100)], [usage(1, 25)])

    def test_unsettled_or_reordered_gateway_events_fail_closed(self):
        with self.assertRaisesRegex(CatalystError, "unsettled"):
            self.project([{"sequence": 1, "source": "gateway", "kind": "model.request",
                           "request_id": "missing"}, evaluation(2, 0, 100)], [], total=0)
        with self.assertRaisesRegex(CatalystError, "order"):
            self.project([charge(2, "call-1", 25), evaluation(1, 25, 100)], [usage(1, 25)])

    def test_exact_budget_and_no_prebudget_observation(self):
        result, _ = self.project([charge(1, "call-1", 20), evaluation(2, 20, 100),
                                 charge(3, "call-2", 5), evaluation(4, 25, 50)],
                                [usage(1, 20), usage(2, 5)])
        self.assertEqual(result["tiers"][0]["best"]["performance"], 100)
        result, _ = self.project([charge(1, "call-1", 25), evaluation(2, 25, 100)], [usage(1, 25)])
        self.assertEqual(result["tiers"][0]["status"], "no_verified_candidate")
