"""Remote subscription removal must not remove local credential support."""
import base64
from contextlib import redirect_stderr
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from openrsi_space.common import OpenRSIError
from openrsi_space.credentials import decode_remote_access, encode_provider_access, require_remote_models
from openrsi_space.cli import build_parser
from openrsi_space.client.evaluations import RemoteClient


class RemoteApiKeysOnlyTests(unittest.TestCase):
    def test_api_key_maps_and_single_api_key_still_work(self):
        for provider in ('openai', 'anthropic', 'openrouter'):
            evaluation = {'model': {'provider': provider, 'name': 'test-model'}}
            expected = {provider: 'synthetic-api-key'}
            self.assertEqual(decode_remote_access(evaluation, encode_provider_access(expected)), expected)
            self.assertEqual(decode_remote_access(evaluation, 'synthetic-api-key'), expected)

    def test_subscription_declared_anywhere_in_model_set_is_rejected(self):
        for provider in ('openai-chatgpt', 'claude-subscription'):
            with self.subTest(provider=provider), self.assertRaisesRegex(OpenRSIError, 'removed'):
                require_remote_models([{'provider': 'openai', 'name': 'api-model'},
                                       {'provider': provider, 'name': 'subscription-model'}])

    def test_legacy_encoded_maps_are_not_accepted_as_api_keys(self):
        evaluation = {'model': {'provider': 'anthropic', 'name': 'test-model'}}
        tokens = ['chatgpt_legacy', 'sk-ant-oat01-synthetic', 'eyJsynthetic.jwt.payload']
        for provider in ('openai-chatgpt', 'claude-subscription'):
            tokens.append('providers_' + base64.urlsafe_b64encode(
                json.dumps({provider: {'access_token': 'synthetic-token'}}).encode()).decode())
        for token in tokens:
            with self.subTest(token=token), self.assertRaises(OpenRSIError):
                decode_remote_access(evaluation, token)

    def test_remote_cli_has_no_codex_login_file_option(self):
        parser, _ = build_parser()
        for command in (['remote', 'submit', '/unused'],):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parser.parse_args(command + ['--codex-auth-file', '/unused/auth.json'])
        args = parser.parse_args(['local', 'run', '/unused', '--dungeness', '/unused/runtime',
                                  '--codex-auth-file', '/unused/auth.json'])
        self.assertEqual(args.codex_auth_file, '/unused/auth.json')

    @patch.dict(os.environ, {"GITHUB_ACTIONS": ""})
    def test_direct_client_rejects_subscription_before_network(self):
        client = RemoteClient.__new__(RemoteClient)
        client.base = 'https://example.invalid'
        client.state = Path('/unused')
        body = {'evaluation': {'model': {'provider': 'openai-chatgpt', 'name': 'test-model'}}}
        with patch('openrsi_space.client.evaluations.request_body', return_value=body), \
             patch('openrsi_space.client.evaluations.transport.solver_fetch') as fetch:
            with self.assertRaisesRegex(OpenRSIError, 'removed'):
                client.submit(Path('/unused'))
            fetch.assert_not_called()

    def test_remote_cli_rejects_removed_access_renewal(self):
        parser, _ = build_parser()
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            parser.parse_args(['remote', 'renew-access', 'unused', '--model-token-stdin'])
        self.assertEqual(raised.exception.code, 2)
