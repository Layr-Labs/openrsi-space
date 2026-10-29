import os
import unittest
from unittest.mock import patch

from catalyst.integrations.dungeness.local import temporary_environment


class OpenRouterLocalAccessTests(unittest.TestCase):
    def test_explicit_assertion_reaches_private_runtime_input_only(self):
        for value, expected in [('1', True), ('0', False), ('', False), ('true', False)]:
            with self.subTest(value=value), patch.dict(os.environ, {
                'TESTBED_OPENROUTER_INFERENCE_ONLY': value,
                'UNRELATED_SECRET': 'synthetic-unrelated-secret',
            }):
                with temporary_environment({'openrouter': 'synthetic-api-key'}) as (path, environment):
                    content = path.read_text()
                    self.assertEqual('TESTBED_OPENROUTER_INFERENCE_ONLY=1\n' in content, expected)
                    self.assertIn('TESTBED_OPENROUTER_API_KEY=synthetic-api-key', content)
                    self.assertNotIn('synthetic-api-key', str(environment))
                    self.assertNotIn('synthetic-unrelated-secret', content + str(environment))
                    self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertFalse(path.exists())

    def test_other_providers_do_not_receive_assertion(self):
        with patch.dict(os.environ, {'TESTBED_OPENROUTER_INFERENCE_ONLY': '1'}):
            with temporary_environment({'openai': 'synthetic-api-key'}) as (path, _):
                self.assertNotIn('OPENROUTER', path.read_text())
