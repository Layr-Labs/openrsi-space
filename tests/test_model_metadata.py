"""Provider selection must not invent capabilities for an arbitrary model."""
from pathlib import Path
import unittest
from unittest.mock import patch

from catalyst.agent_setup import model_profile
from catalyst.common import CatalystError


class ModelMetadataTests(unittest.TestCase):
    def test_new_model_does_not_inherit_codex_context_or_reasoning_limits(self):
        pricing = {"entries": [{
            "provider": "openai-chatgpt", "upstream_id": "example-new-model",
            "request_models": ["example-new-model"],
        }]}
        with patch("catalyst.integrations.dungeness.providers.model_providers", return_value={"openai-chatgpt"}):
            profile = model_profile(Path("/unused"), "example-new-model", "openai-chatgpt", pricing)
        self.assertNotIn("context_window", profile)
        self.assertNotIn("supported_reasoning_efforts", profile)

    def test_retired_providers_cannot_create_execution_profiles(self):
        for provider in ("moonshot", "kimi-code", "xai", "grok-subscription"):
            with self.subTest(provider=provider):
                pricing = {"entries": [{
                    "provider": provider, "upstream_id": provider + "/example",
                    "request_models": ["example"],
                }]}
                with self.assertRaisesRegex(CatalystError, "retired"):
                    model_profile(Path("/unused"), "example", provider, pricing)

    def test_retired_provider_history_is_readable_but_credentials_are_rejected(self):
        from catalyst.credentials import validate_provider_access
        from catalyst.remote import validate_model
        for provider, name in (("moonshot", "kimi-k3"), ("kimi-code", "k3")):
            with self.subTest(provider=provider):
                validate_model({"provider": provider, "name": name})
                with self.assertRaisesRegex(CatalystError, "supported providers"):
                    validate_provider_access({provider: "offline-test-credential"})

    def test_retired_xai_and_grok_history_uses_its_retained_prices(self):
        from catalyst.remote import validate_model
        from catalyst.credentials import require_active_models
        for provider in ("xai", "grok-subscription"):
            model = {"provider": provider, "name": "historical-model"}
            pricing = {"entries": [{"provider": provider, "request_models": [model["name"]],
                                    "input_per_mtok": 2, "output_per_mtok": 6}]}
            validate_model(model, pricing=pricing)
            with self.assertRaisesRegex(CatalystError, "retired"):
                require_active_models([model])
