"""Budget views and credit contracts; all data synthetic, no provider calls."""
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest

from catalyst.common import CatalystError, write_json
from catalyst.tiers import credits, pricing_digest, project_observation, SCORING, VALIDITY
from catalyst.remote import evaluation_config

MODEL = {"provider": "openai", "name": "gpt-5.6-sol"}
LIMITS = {"max_model_tokens": 1_000_000_000, "max_seconds": 900}


def usage(sequence, cost):
    # Sol's pinned uncached input rate is 5 credits / million tokens.
    return {"sequence": sequence, "request_id": f"call-{sequence}", "settled": True,
            "tokens": {"input_tokens": int(Decimal(str(cost)) * 200_000), "output_tokens": 0,
                       "cached_read_tokens": 0, "cache_write_tokens": 0}}


def candidate(sequence, cost, performance):
    return {"captured_sequence": sequence, "candidate_digest": f"{sequence:064x}",
            "verified_candidate_digest": f"{sequence:064x}", "verified": True, "settled": True,
            "avg_toffoli": performance / 10, "peak_qubits": 10, "performance": performance,
            "normalized_model_usd": cost}


def observation():
    # Legacy seals no longer restrict budget views; both $20 candidates qualify.
    return {
        "pricing_digest": pricing_digest(), "end_sequence": 13,
        "normalized_model_usd": 201,
        "usage": [usage(1, 20), usage(5, 0.01), usage(7, 179.99), usage(10, 1)],
        "checkpoints": [{"budget_tier": b, "sequence": s, "settled": True}
                        for b, s in ((20, 3), (200, 9))],
        "curve": [candidate(2, 20, 1000), candidate(4, 20, 900),
                  candidate(6, 20.01, 800), candidate(8, 200, 700), candidate(11, 201, 600),
                  candidate(12, 201, 750)],
    }


class TierTests(unittest.TestCase):
    def project(self, record=None, budget=500):
        return project_observation(record if record is not None else observation(), MODEL, budget, LIMITS)

    def test_inclusive_boundaries_and_late_capture_cannot_improve_earlier_tiers(self):
        result = self.project()
        self.assertEqual([t["budget_tier"] for t in result["tiers"]], [10, 20, 50, 100])
        self.assertEqual([t["best"]["performance"] if t["best"] else None for t in result["tiers"]],
                         [None, 900, 800, 800])
        self.assertEqual([t["best"]["normalized_model_usd"] if t["best"] else None for t in result["tiers"]],
                         [None, 20, 20.01, 20.01])
        self.assertEqual(result["best"]["performance"], 600)
        self.assertEqual(len(result["curve"]), 6)  # Includes regressions and same-cost captures.
        self.assertEqual(result["normalized_model_usd"], 201)

    def test_views_need_no_seals_and_a_cheaper_run_qualifies_for_all(self):
        record = observation()
        record["checkpoints"] = []
        result = self.project(record)
        self.assertEqual([t["status"] for t in result["tiers"]],
                         ["no_verified_candidate", "eligible", "eligible", "eligible"])
        record["curve"] = [p for p in record["curve"] if p["normalized_model_usd"] > 20]
        record["checkpoints"] = observation()["checkpoints"]
        self.assertEqual(self.project(record)["tiers"][0]["status"], "no_verified_candidate")
        record = observation()
        record.update(usage=[usage(1, 5)], normalized_model_usd=5,
                      checkpoints=[], curve=[candidate(2, 5, 1000)], end_sequence=3)
        self.assertEqual([t["status"] for t in self.project(record, 5)["tiers"]],
                         ["eligible"] * 4)

    def test_all_four_exact_boundaries_keep_later_improvements_and_regressions_separate(self):
        captures = [(10, 1000), (10, 999), (10.01, 900), (20, 800), (20.01, 700),
                    (50, 600), (50.01, 500), (100, 400), (100.01, 300), (500, 100), (500, 120)]
        ledger, curve, previous = [], [], Decimal(0)
        for i, (cost, score) in enumerate(captures):
            ledger.append(usage(i * 2 + 1, Decimal(str(cost)) - previous))
            curve.append(candidate(i * 2 + 2, cost, score))
            previous = Decimal(str(cost))
        record = {"pricing_digest": pricing_digest(), "end_sequence": len(captures) * 2,
                  "usage": ledger, "curve": curve, "normalized_model_usd": 500, "checkpoints": []}
        result = self.project(record, 500)
        self.assertEqual([t["best"]["performance"] for t in result["tiers"]], [999, 800, 600, 400])
        self.assertEqual([t["best"]["normalized_model_usd"] for t in result["tiers"]], [10, 20, 50, 100])
        self.assertEqual(result["best"]["performance"], 100)
        self.assertEqual(len(result["curve"]), len(captures))

    def test_legacy_200_seal_is_preserved_without_becoming_a_display_tier(self):
        result = self.project()
        self.assertEqual(result["checkpoints"][-1]["budget_tier"], 200)
        self.assertNotIn(200, [t["budget_tier"] for t in result["tiers"]])

    def test_no_candidate_does_not_get_a_baseline_or_zero(self):
        record = observation()
        record["curve"] = []
        self.assertTrue(all(t["best"] is None for t in self.project(record)["tiers"]))
        self.assertIsNone(self.project(record)["best"])

    def test_best_achieved_has_no_fixed_budget_cutoff_and_keeps_later_usage(self):
        record = {"pricing_digest": pricing_digest(), "end_sequence": 6,
                  "normalized_model_usd": 2600, "usage": [usage(1, 2500), usage(4, 100)],
                  "checkpoints": [],
                  "curve": [candidate(2, 2500, 100), candidate(5, 2600, 150)]}
        result = self.project(record, 3000)
        self.assertEqual(result["best"]["performance"], 100)
        self.assertEqual(result["best"]["normalized_model_usd"], 2500)
        self.assertEqual(result["normalized_model_usd"], 2600)
        self.assertEqual(len(result["curve"]), 2)
        self.assertTrue(all(t["status"] == "no_verified_candidate" for t in result["tiers"]))

    def test_legacy_seals_do_not_exclude_an_observation_at_the_budget(self):
        record = observation()
        record["curve"][1].update(avg_toffoli=1, performance=10)
        result = self.project(record)
        self.assertEqual(result["best"]["performance"], 10)
        self.assertEqual(result["tiers"][1]["best"]["performance"], 10)

    def test_accounting_and_capture_tampering_fail_closed(self):
        mutations = [
            lambda r: r.update(pricing_digest="f" * 64),
            lambda r: r.update(normalized_model_usd=200),
            lambda r: r["usage"][1].update(sequence=1),
            lambda r: r["usage"][1].update(request_id="call-1"),
            lambda r: r["usage"][0].update(settled=False),
            lambda r: r["curve"][0].update(settled=False),
            lambda r: r["curve"][0].update(verified=False),
            lambda r: r["curve"][0].update(verified_candidate_digest="f" * 64),
            lambda r: r["curve"][0].update(normalized_model_usd=19.99),
            lambda r: r["curve"][0].update(captured_sequence=1),
            lambda r: r["curve"][0].update(avg_toffoli=1),
            lambda r: r["curve"][0].update(peak_qubits=True),
            lambda r: r["curve"][0].update(performance=float("inf")),
            lambda r: r["curve"][0].update(performance=0, avg_toffoli=0),
            lambda r: r["checkpoints"][0].update(sequence=6),  # Usage already > 20.
            lambda r: r["checkpoints"][0].update(settled=False),
            lambda r: r["checkpoints"].reverse(),
            lambda r: r.update(end_sequence=10),
        ]
        for mutation in mutations:
            record = observation()
            mutation(record)
            with self.subTest(mutation=mutation), self.assertRaises(CatalystError):
                self.project(record)

    def test_overrun_and_unknown_usage_never_silently_round_down(self):
        record = observation()
        record["usage"][0]["tokens"]["input_tokens"] += 1
        record["normalized_model_usd"] = 201.000005
        with self.assertRaises(CatalystError):
            self.project(record)  # The earlier capture is now > 20 and disagrees.
        with self.assertRaises(CatalystError):
            self.project(observation(), 200)  # 201 total credits exceeds authority.
        with self.assertRaises(CatalystError):
            project_observation(observation(), MODEL, 500, {**LIMITS, "max_model_tokens": 10})
        record = observation()
        record["usage"][0]["tokens"].pop("output_tokens")
        with self.assertRaises(CatalystError):
            self.project(record)

    def test_native_token_budget_uses_trusted_counter_without_changing_credits(self):
        record = observation()
        for event in record["usage"]:
            event["budget_tokens"] = 100
        result = project_observation(record, MODEL, 500, {**LIMITS, "max_model_tokens": 400})
        self.assertEqual(result["normalized_model_usd"], 201)
        with self.assertRaises(CatalystError):
            project_observation(record, MODEL, 500, {**LIMITS, "max_model_tokens": 399})
        with self.assertRaises(CatalystError):
            project_observation(record, MODEL, 200, {**LIMITS, "max_model_tokens": 400})


class PricingTests(unittest.TestCase):
    def test_provider_routes_and_subscriptions_use_same_reference_credit_rates(self):
        tokens = {"input_tokens": 1_000_000, "output_tokens": 100_000,
                  "cached_read_tokens": 200_000, "cache_write_tokens": 0}
        for model in (MODEL, {"provider": "openai-chatgpt", "name": "gpt-5.6-sol"},
                      {"provider": "openrouter", "name": "openai/gpt-5.6-sol"}):
            self.assertEqual(credits(tokens, model), Decimal("7.1"))

    def test_cache_writes_and_long_context_price_the_whole_request(self):
        model = {"provider": "openai", "name": "gpt-6-astra"}
        tokens = {"input_tokens": 272000, "output_tokens": 1000,
                  "cached_read_tokens": 2000, "cache_write_tokens": 1000}
        self.assertEqual(credits(tokens, model), Decimal("2.7545"))
        tokens["input_tokens"] += 1
        self.assertEqual(credits(tokens, model), Decimal("5.48402"))

    def test_bad_counts_unknown_models_and_unpriced_buckets_are_rejected(self):
        base = {"input_tokens": 100, "output_tokens": 10, "cached_read_tokens": 0, "cache_write_tokens": 0}
        for override in ({"input_tokens": True}, {"output_tokens": -1},
                         {"output_tokens": 1.5}, {"cached_read_tokens": 101},
                         {"cache_write_tokens": 1}, {"extra": 1}):
            with self.assertRaises(CatalystError):
                credits({**base, **override}, MODEL)
        with self.assertRaises(CatalystError):
            credits(base, {"provider": "unpriced", "name": "any"})

    def test_config_requires_explicit_finite_credit_cap_and_pinned_prices(self):
        source = Path(__file__).resolve().parents[1]
        config = json.loads((source / "submission/evaluation.json").read_text())
        config["llm_access"]["grant_id"] = "grant_test_only"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evaluation.json"
            for value in (20, 200, 3000, 1, 20.5, 0, -1, "20", True, None, float("inf")):
                modified = {**config, "max_model_credits": value}
                # Non-finite input is parsed only to prove validation rejects it.
                path.write_text(json.dumps(modified))
                if type(value) in (int, float) and 0 < value < float("inf"):
                    self.assertEqual(evaluation_config(path), modified)
                else:
                    with self.assertRaises(CatalystError):
                        evaluation_config(path)
            write_json(path, {**config, "model": {"provider": "openai", "name": "unpriced"}})
            with self.assertRaises(CatalystError):
                evaluation_config(path)
        manifest = json.loads((source / "benchmark.json").read_text())
        self.assertEqual(manifest["paretoPolicies"], {"scoring": SCORING, "validity": VALIDITY})
        self.assertEqual(manifest["schemaVersion"], 1)
        self.assertEqual(manifest["promotionMode"], "automatic")
        self.assertEqual(manifest["editablePaths"], ["submission/verification.json"])
        self.assertEqual(manifest["runner"]["provider"], "github-actions")
        self.assertEqual([o["name"] for o in manifest["objectives"]], ["ecdsaPerformance", "modelCreditsAtBest"])
