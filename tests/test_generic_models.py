"""Generic harness contracts; synthetic usage only, no paid calls."""
import copy
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from catalyst.common import CatalystError, write_json
from catalyst.ecdsa_history import project_history
from catalyst.live_provider import ProviderAccess, encode_provider_access
from catalyst.remote import validate_evaluation_config
from catalyst.tiers import pricing_digest, project_observation
from catalyst.worker import collect_usage
from test_tiers import candidate, LIMITS


MODELS = [{"provider": "openai", "name": "gpt-5.6-sol"},
          {"provider": "openai", "name": "gpt-6-astra"}]
CONFIG = {"schema_version": 4, "model": MODELS[0], "models": MODELS,
          "llm_access": {"grant_id": "grant_temporary_provider"},
          "max_model_credits": 30, "limits": LIMITS}


class GenericModelsTests(unittest.TestCase):
    def test_versioned_model_set_rejects_unpriced_duplicate_or_undeclared_default(self):
        validate_evaluation_config(CONFIG)
        for models in ([], [MODELS[1]], MODELS + [MODELS[0]],
                       MODELS + [{"provider": "unknown", "name": "free-model"}]):
            with self.subTest(models=models), self.assertRaises(CatalystError):
                validate_evaluation_config({**CONFIG, "models": models})
        with self.assertRaises(CatalystError):
            validate_evaluation_config({**CONFIG, "schema_version": 3})

    def test_two_models_and_inflight_work_cannot_claim_early_budget_score(self):
        def charge(sequence, request, model, input_tokens, cost):
            return {"sequence": sequence, "source": "gateway", "kind": "model.accounting",
                    "request_id": request, "data": {
                        "provider": model["provider"], "model": model["name"],
                        "accounting_method": "gateway", "input_tokens": input_tokens,
                        "output_tokens": 0, "cached_input_tokens": 0,
                        "cache_write_input_tokens": 0, "normalized_usd": cost}}

        def point(sequence, cost, score):
            return {"sequence": sequence, "source": "evaluator", "kind": "evaluation.completed",
                    "usage": {"normalized_usd": cost}, "data": {
                        "operation": "score", "status": "ok", "candidate_sha256": "a" * 64,
                        "source_sha256": "b" * 64, "avg_toffoli": score / 10,
                        "peak_qubits": 10, "score": score}}
        # Astra long-context rate is 20/million: 300k input tokens cost 6.
        events = [charge(1, "worker-a", MODELS[0], 3_800_000, 19),
                  point(2, 19, 100),
                  {"sequence": 3, "source": "gateway", "kind": "model.request", "request_id": "worker-b"},
                  point(4, 19, 50), charge(5, "worker-b", MODELS[1], 300_000, 6)]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "usage").mkdir()
            (root / "usage/events.jsonl").write_text("\n".join(map(json.dumps, events)))
            write_json(root / "record.json", {"data": {"usage": {"normalized_usd": 25}}})
            ledger, total = collect_usage(root, CONFIG)
            self.assertEqual(total, Decimal(25))
            ledger, curve, end, _ = project_history(root, ledger, [], MODELS)
            result = project_observation({
                "pricing_digest": pricing_digest(), "normalized_model_usd": 25,
                "usage": ledger, "curve": curve, "end_sequence": end,
            }, MODELS, 30, LIMITS)
            self.assertEqual([p["normalized_model_usd"] for p in result["curve"]], [19, 25])
            self.assertEqual(result["tiers"][0]["best"]["performance"], 100)
            self.assertEqual(result["best"]["performance"], 50)
            with self.assertRaisesRegex(CatalystError, "authorized model set"):
                collect_usage(root, {**CONFIG, "models": [MODELS[0]]})

    def test_mixed_usage_cannot_omit_or_forge_model_identity(self):
        from test_tiers import usage
        record = {"pricing_digest": pricing_digest(), "normalized_model_usd": 1,
                  "end_sequence": 3, "usage": [usage(1, 1)], "curve": [candidate(2, 1, 100)]}
        with self.assertRaises(CatalystError):
            project_observation(record, MODELS, 2, LIMITS)
        record["usage"][0]["model"] = MODELS[0]
        project_observation(record, MODELS, 2, LIMITS)
        record["usage"][0]["model"] = {"provider": "anthropic", "name": "claude-opus-5"}
        with self.assertRaises(CatalystError):
            project_observation(record, MODELS, 2, LIMITS)

    def test_private_access_must_cover_exact_provider_set(self):
        context = ProviderAccess(CONFIG, "synthetic-openai-token")
        self.assertEqual(context.access, {"openai": "synthetic-openai-token"})
        multi = copy.deepcopy(CONFIG)
        multi["models"].append({"provider": "anthropic", "name": "claude-opus-5"})
        credential = encode_provider_access({
            "openai": "synthetic-openai-token", "anthropic": "synthetic-anthropic-token"})
        self.assertEqual(set(ProviderAccess(multi, credential).access), {"openai", "anthropic"})
        with self.assertRaises(CatalystError):
            ProviderAccess(CONFIG, credential)
        with self.assertRaises(CatalystError):
            ProviderAccess(multi, "synthetic-openai-token")
        for token in ("bad\nENV=secret", "bad${INJECTION}", "bad'quoted"):
            with self.assertRaises(CatalystError):
                encode_provider_access({"openai": token})

    def test_hosted_policy_checks_every_model_provider(self):
        from catalyst.hosted import ServiceIdentity
        from catalyst.evaluator import APIError
        # authorize_run needs only configuration and authenticated identity.
        identity = object.__new__(ServiceIdentity)
        identity.config = {"model_policy": {"enabled": True, "providers": ["openai"], "limits": LIMITS}}
        principal = {"kind": "yukon-solver", "authentication": "yukon"}
        request = {"context": {"kind": "yukon-solver"}, "evaluation": copy.deepcopy(CONFIG)}
        identity.authorize_run(principal, request)
        request["evaluation"]["models"].append({"provider": "anthropic", "name": "claude-opus-5"})
        with self.assertRaises(APIError):
            identity.authorize_run(principal, request)

    def test_provider_staging_is_private_and_removed_on_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            staged = Path(temporary) / "ram-fixture"
            staged.mkdir()
            context = ProviderAccess(CONFIG, "synthetic-openai-token")
            with patch("catalyst.live_provider.subprocess.check_output", return_value="tmpfs\n"), \
                    patch("catalyst.live_provider.tempfile.mkdtemp", return_value=str(staged)) as create:
                with self.assertRaisesRegex(RuntimeError, "fixture"):
                    with context as access:
                        self.assertEqual(create.call_args.kwargs["dir"], "/dev/shm")
                        self.assertEqual(access.env_file.stat().st_mode & 0o777, 0o600)
                        self.assertEqual(staged.stat().st_mode & 0o777, 0o700)
                        self.assertIsNone(access.auth_file)
                        self.assertEqual(access.env_file.read_text(),
                                         "TESTBED_OPENAI_API_KEY=synthetic-openai-token\n")
                        raise RuntimeError("fixture")
            self.assertFalse(staged.exists())
            self.assertEqual(context.access, {})
