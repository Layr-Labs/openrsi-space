import unittest
from openrsi_space.contracts.model_equivalence import model_binding, public_policy


class ModelEquivalenceTests(unittest.TestCase):
    def test_published_pairs_match_only_with_same_effort(self):
        for group in public_policy()['equivalences']:
            for local in group['local']:
                remote = group['remote']
                with self.subTest(local=local):
                    self.assertEqual(model_binding([{**local, 'reasoning_effort': 'high'}]),
                                     model_binding([{**remote, 'reasoning_effort': 'high'}]))
                    self.assertNotEqual(model_binding([local]),
                                        model_binding([{**remote, 'reasoning_effort': 'high'}]))

    def test_unknown_routes_aliases_dates_and_model_sets_stay_distinct(self):
        expected = model_binding([{'provider': 'openrouter', 'name': 'openai/gpt-6-astra'}])
        for provider, name in [('other', 'gpt-6-astra'), ('openai-chatgpt', 'gpt-6-astra-latest'),
                               ('openai-chatgpt', 'gpt-6-astra-20261030'),
                               ('claude-subscription', 'gpt-6-astra')]:
            self.assertNotEqual(model_binding([{'provider': provider, 'name': name}]), expected)
        model = {'provider': 'openai-chatgpt', 'name': 'gpt-6-astra'}
        self.assertNotEqual(model_binding([model, model]), expected)
        self.assertEqual(model_binding([{'provider': 'openrouter', 'name': 'vendor/new-model'}]),
                         [('openrouter', 'vendor/new-model', '')])
