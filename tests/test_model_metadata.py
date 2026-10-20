"""Provider selection must not invent capabilities for an arbitrary model."""
from pathlib import Path
import unittest

from catalyst.agent_setup import model_profile


class ModelMetadataTests(unittest.TestCase):
    def test_new_model_does_not_inherit_codex_context_or_reasoning_limits(self):
        pricing = {"entries": [{
            "provider": "openai-chatgpt", "upstream_id": "example-new-model",
            "request_models": ["example-new-model"],
        }]}
        profile = model_profile(Path("/unused"), "example-new-model", "openai-chatgpt", pricing)
        self.assertNotIn("context_window", profile)
        self.assertNotIn("supported_reasoning_efforts", profile)

    def test_native_kimi_models_no_longer_advertise_removed_responses_adapter(self):
        for provider in ("moonshot", "kimi-code"):
            with self.subTest(provider=provider):
                pricing = {"entries": [{
                    "provider": provider, "upstream_id": provider + "/example",
                    "request_models": ["example"],
                }]}
                profile = model_profile(Path("/unused"), "example", provider, pricing)
                self.assertEqual(profile["api"], "openai-completions")
