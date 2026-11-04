"""Admission-based credit limits; no provider calls."""
import copy
from decimal import Decimal
import json
import unittest

from openrsi_space.common import OpenRSIError
from openrsi_space.remote import judge_input, judgment
from openrsi_space.tiers import LEGACY_VALIDITY, SCORING, VALIDITY, pricing_digest, pricing_schedule, project_observation
from test_tiers import MODEL, LIMITS, candidate, usage


def observation(costs=(2.95, .52), boundaries=(None, "call-1")):
    ledger = [dict(usage(i, cost), admitted_after=boundary)
              for i, (cost, boundary) in enumerate(zip(costs, boundaries), 1)]
    total = float(sum(Decimal(str(cost)) for cost in costs))
    return {"pricing_digest": pricing_digest(), "end_sequence": len(ledger) + 1,
            "usage": ledger, "normalized_model_usd": total,
            "curve": [candidate(len(ledger) + 1, total, 100)]}


class InflightBudgetTests(unittest.TestCase):
    def project(self, record, cap=3, **kwargs):
        return project_observation(record, MODEL, cap, LIMITS, **kwargs)

    def test_last_response_and_concurrent_responses_keep_actual_cost(self):
        for record in (observation(), observation((2.9, .3, .27), (None, "call-1", "call-1"))):
            with self.subTest(record=record):
                result = self.project(record)
                self.assertEqual(result["normalized_model_usd"], 3.47)
                self.assertEqual(result["best"]["normalized_model_usd"], 3.47)

    def test_crossing_a_display_budget_does_not_make_the_candidate_eligible(self):
        result = self.project(observation((9.9, .2)), cap=10)
        self.assertEqual(result["tiers"][0]["status"], "no_verified_candidate")
        self.assertEqual(result["tiers"][1]["best"]["normalized_model_usd"], 10.1)

    def test_missing_invalid_or_late_admission_fails_closed(self):
        records = [observation((3, .1)), observation((3.1, .1))]
        for boundary in ("missing", "call-2", [], 42):
            record = observation()
            record["usage"][1]["admitted_after"] = boundary
            records.append(record)
        record = observation()
        del record["usage"][0]["admitted_after"]
        records.append(record)
        for record in records:
            with self.subTest(record=record), self.assertRaises(OpenRSIError):
                self.project(record)

    def test_legacy_cap_clipping_and_token_overruns_still_fail(self):
        with self.assertRaises(OpenRSIError):
            self.project(observation(), allow_inflight_overshoot=False)
        record = observation()
        record["normalized_model_usd"] = 3
        with self.assertRaises(OpenRSIError):
            self.project(record)
        with self.assertRaisesRegex(OpenRSIError, "token limit"):
            project_observation(observation(), MODEL, 3, {**LIMITS, "max_model_tokens": 1})
        # New optional evidence must not alter v2's original validation rules.
        record = observation((1, 1), (None, "unknown"))
        self.project(record, allow_inflight_overshoot=False)

    def test_judgment_preserves_explicit_legacy_policy(self):
        problem = {"id": "test", "repository": {"commit": "a" * 40}}
        record = dict(observation(), problem_id="test", problem_commit="a" * 40)
        result = {"status": "completed", "evaluation_id": "test", "valid": True, "reason": "verified",
                  "trace_available": True, "observations": [record],
                  "build": {"id": "test", "image_digest": "sha256:" + "a" * 64}}
        request = {"judge": judge_input(None), "problem_set": [problem], "pricing": pricing_schedule(),
                   "source": {"digest": "b" * 64}, "evaluation": {
                       "model": MODEL, "max_model_credits": 3, "limits": LIMITS}}
        judgment(result, request)
        legacy = copy.deepcopy(request)
        legacy["judge"]["policies"]["validity"] = LEGACY_VALIDITY
        self.assertEqual(judge_input(json.dumps(legacy["judge"])), legacy["judge"])
        with self.assertRaisesRegex(OpenRSIError, "credit limit"):
            judgment(result, legacy)
        self.assertEqual(judge_input(None)["policies"], {"scoring": SCORING, "validity": VALIDITY})
        legacy["judge"]["policies"]["validity"] = {"version": "unknown"}
        with self.assertRaises(OpenRSIError):
            judge_input(json.dumps(legacy["judge"]))
