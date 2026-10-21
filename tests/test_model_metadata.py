"""Provider selection must not invent capabilities for an arbitrary model."""
from pathlib import Path
import unittest

from catalyst.agent_setup import model_profile
from catalyst.common import CatalystError


class ModelMetadataTests(unittest.TestCase):
    def test_new_model_does_not_inherit_codex_context_or_reasoning_limits(self):
        pricing = {"entries": [{
            "provider": "openai-chatgpt", "upstream_id": "example-new-model",
            "request_models": ["example-new-model"],
        }]}
        profile = model_profile(Path("/unused"), "example-new-model", "openai-chatgpt", pricing)
        self.assertNotIn("context_window", profile)
        self.assertNotIn("supported_reasoning_efforts", profile)

    def test_retired_providers_cannot_create_execution_profiles(self):
        for provider in ("moonshot", "kimi-code"):
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
