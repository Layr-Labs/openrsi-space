import base64
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from catalyst.common import CatalystError
from catalyst.credentials import grok_access, encode_grok_access, ACCESS_PREFIX, validate_provider_access
from catalyst.cli import build_parser, model_access_input
from catalyst.local import temporary_environment
from catalyst.provider_profiles import load_profiles, PROFILE_PATH

class GrokAccessTests(unittest.TestCase):
    def test_device_session_export_never_exports_refresh_or_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'auth.json'
            expiry = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
            entry = {'key': 'temporary-session-only', 'auth_mode': 'oidc', 'expires_at': expiry,
                     'oidc_issuer': 'https://auth.x.ai', 'refresh_token': 'keep-refresh-local',
                     'user_id': 'keep-identity-local'}
            path.write_text(json.dumps({'https://auth.x.ai::firstparty': entry}))
            encoded = encode_grok_access(path)
            decoded = json.loads(base64.urlsafe_b64decode(encoded[len(ACCESS_PREFIX):]))
            self.assertEqual(decoded, {'grok-subscription': {'access_token': entry['key'], 'expires_at': expiry}})
            self.assertIn('keep-refresh-local', path.read_text())
            for command in [['remote', 'submit', '/harness'], ['remote', 'renew-access', 'job'],
                            ['local', 'run', '/harness', '--dungeness', '/runtime']]:
                args = build_parser()[0].parse_args(command + ['--grok-auth-file', str(path)])
                self.assertEqual(model_access_input(args), encoded)
            with temporary_environment(decoded) as (env_file, environment):
                self.assertIn('TESTBED_GROK_SUBSCRIPTION_TOKEN=temporary-session-only', env_file.read_text())
                self.assertIn('TESTBED_GROK_SUBSCRIPTION_TOKEN_EXPIRES_AT=', env_file.read_text())
                self.assertNotIn('temporary-session-only', json.dumps(environment))
                self.assertNotIn('refresh', env_file.read_text())
            self.assertFalse(env_file.exists())
            for changes in ({'auth_mode': 'api_key'}, {'key': 'xai-not-a-session'},
                            {'expires_at': '2000-01-01T00:00:00Z'}, {'oidc_issuer': 'https://evil.invalid'}):
                path.write_text(json.dumps({'https://auth.x.ai::firstparty': {**entry, **changes}}))
                with self.subTest(changes=changes), self.assertRaises(CatalystError):
                    grok_access(path)
            path.write_text(json.dumps({'https://auth.x.ai::a': entry, 'https://auth.x.ai::b': entry}))
            with self.assertRaises(CatalystError): grok_access(path)

    def test_subscription_rejects_raw_keys_and_expiry_injection(self):
        for value in ('api-token-string', {'access_token': 'temporary-session', 'expires_at': '2099-01-01\n00:00:00+00:00'},
                      {'access_token': 'temporary-session', 'expires_at': '2099-01-01T00:00:00Z', 'refresh_token': 'secret'}):
            with self.subTest(value=value), self.assertRaises(CatalystError):
                validate_provider_access({'grok-subscription': value})

    def test_compatible_provider_can_be_added_with_configuration(self):
        document = json.loads(PROFILE_PATH.read_text())
        profile = {**document['providers']['xai'], 'base_url': 'https://example.invalid/v1',
                   'credential_env': 'EXAMPLE_API_KEY', 'catalog_author': 'example'}
        document['providers']['example'] = profile
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'providers.json'; path.write_text(json.dumps(document))
            self.assertEqual(load_profiles(path)['example'], profile)
            for changes in ({'base_url': 'http://example.invalid/v1'}, {'routes': ['search']},
                            {'headers': {'authorization': 'secret'}}, {'credential_env': 'XAI_API_KEY'}):
                document['providers']['example'] = {**profile, **changes}
                path.write_text(json.dumps(document))
                with self.subTest(changes=changes), self.assertRaises(ValueError): load_profiles(path)

    def test_authentication_header_configuration_is_trusted_and_collision_free(self):
        document = json.loads(PROFILE_PATH.read_text())
        profile = {**document['providers']['xai'],
                   'credential_header': 'x-api-key', 'credential_prefix': '',
                   'credential_headers': {'account-id': 'XAI_API_KEY_ACCOUNT'}}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'providers.json'
            document['providers']['xai'] = profile
            path.write_text(json.dumps(document))
            self.assertEqual(load_profiles(path)['xai'], profile)
            for changes in (
                {'credential_header': 'host'},
                {'credential_prefix': 'Bearer\r\nInjected: '},
                {'headers': {'x-api-key': 'override'}},
                {'credential_headers': {'account-id': 'OPENAI_API_KEY'}},
                {'credential_headers': {'host': 'XAI_API_KEY_ACCOUNT'}},
                {'credential_headers': {'authorization': 'XAI_API_KEY_ACCOUNT'}},
                {'credential_headers': {'account-id': 'XAI_API_KEY_EXPIRES_AT'}},
            ):
                document['providers']['xai'] = {**profile, **changes}
                path.write_text(json.dumps(document))
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    load_profiles(path)
