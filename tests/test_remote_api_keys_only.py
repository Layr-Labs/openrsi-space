"""Remote subscription removal must not remove local credential support."""
import base64
from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from catalyst.common import CatalystError
from catalyst.credentials import decode_remote_access, encode_provider_access, require_remote_models
from catalyst.cli import build_parser
from catalyst.client.evaluations import RemoteClient


class RemoteApiKeysOnlyTests(unittest.TestCase):
    def test_api_key_maps_and_single_api_key_still_work(self):
        for provider in ('openai', 'anthropic', 'openrouter'):
            evaluation = {'model': {'provider': provider, 'name': 'test-model'}}
            expected = {provider: 'synthetic-api-key'}
            self.assertEqual(decode_remote_access(evaluation, encode_provider_access(expected)), expected)
            self.assertEqual(decode_remote_access(evaluation, 'synthetic-api-key'), expected)

    def test_subscription_declared_anywhere_in_model_set_is_rejected(self):
        for provider in ('openai-chatgpt', 'claude-subscription'):
            with self.subTest(provider=provider), self.assertRaisesRegex(CatalystError, 'removed'):
                require_remote_models([{'provider': 'openai', 'name': 'api-model'},
                                       {'provider': provider, 'name': 'subscription-model'}])

    def test_legacy_encoded_maps_are_not_accepted_as_api_keys(self):
        evaluation = {'model': {'provider': 'anthropic', 'name': 'test-model'}}
        tokens = ['chatgpt_legacy', 'sk-ant-oat01-synthetic', 'eyJsynthetic.jwt.payload']
        for provider in ('openai-chatgpt', 'claude-subscription'):
            tokens.append('providers_' + base64.urlsafe_b64encode(
                json.dumps({provider: {'access_token': 'synthetic-token'}}).encode()).decode())
        for token in tokens:
            with self.subTest(token=token), self.assertRaises(CatalystError):
                decode_remote_access(evaluation, token)

    def test_remote_cli_has_no_codex_login_file_option(self):
        parser, _ = build_parser()
        for command in (['remote', 'submit', '/unused'], ['remote', 'renew-access', 'unused']):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parser.parse_args(command + ['--codex-auth-file', '/unused/auth.json'])
        args = parser.parse_args(['local', 'run', '/unused', '--dungeness', '/unused/runtime',
                                  '--codex-auth-file', '/unused/auth.json'])
        self.assertEqual(args.codex_auth_file, '/unused/auth.json')

    def test_direct_client_rejects_subscription_before_network(self):
        client = RemoteClient.__new__(RemoteClient)
        client.base = 'https://example.invalid'
        client.state = Path('/unused')
        body = {'evaluation': {'model': {'provider': 'openai-chatgpt', 'name': 'test-model'}}}
        with patch('catalyst.client.evaluations.request_body', return_value=body), \
             patch('catalyst.client.evaluations.transport.solver_fetch') as fetch:
            with self.assertRaisesRegex(CatalystError, 'removed'):
                client.submit(Path('/unused'))
            fetch.assert_not_called()
        with patch.object(client, 'session', return_value={'request': body}), \
             patch('pathlib.Path.is_file', return_value=True), \
             patch('catalyst.client.evaluations.transport.solver_fetch') as fetch:
            with self.assertRaisesRegex(CatalystError, 'removed'):
                client.renew_access('00000000-0000-4000-8000-000000000001', 'synthetic-token')
            fetch.assert_not_called()
