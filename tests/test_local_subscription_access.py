"""Local subscription credentials must never enter remote handoff or source."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from openrsi_space.common import OpenRSIError
from openrsi_space.credentials import (grok_access, validate_provider_access,
                                  encode_provider_access, require_remote_models)
from openrsi_space.integrations.dungeness.local import temporary_environment, credential_input
from openrsi_space.cli import build_parser


class LocalSubscriptionAccessTests(unittest.TestCase):
    def test_grok_login_export_staging_and_remote_rejection(self):
        expiry = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        entry = {'key': 'synthetic-session-key', 'expires_at': expiry,
                 'auth_mode': 'oidc', 'oidc_issuer': 'https://auth.x.ai',
                 'refresh_token': 'never-export-refresh', 'user_id': 'private-account'}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'auth.json'
            path.write_text(json.dumps({'https://auth.x.ai::client': entry}))
            value = grok_access(path)
            self.assertEqual(value, {'access_token': entry['key'], 'expires_at': expiry})
            access = {'grok-subscription': value}
            validate_provider_access(access)
            with self.assertRaises(OpenRSIError):
                encode_provider_access(access)
            with temporary_environment(access) as (env_file, environment):
                self.assertEqual(env_file.stat().st_mode & 0o777, 0o600)
                self.assertIn('TESTBED_GROK_SUBSCRIPTION_TOKEN=', env_file.read_text())
                self.assertNotIn(entry['key'], json.dumps(environment))
                self.assertNotIn('never-export-refresh', env_file.read_text())
            self.assertFalse(env_file.exists())
            for change in ({'expires_at': '2000-01-01T00:00:00Z'},
                           {'auth_mode': 'api_key'}, {'oidc_issuer': 'https://other.invalid'}):
                path.write_text(json.dumps({'https://auth.x.ai::client': {**entry, **change}}))
                with self.subTest(change=change), self.assertRaises(OpenRSIError):
                    grok_access(path)
            path.write_text(json.dumps({'https://auth.x.ai::a': entry, 'https://auth.x.ai::b': entry}))
            with self.assertRaises(OpenRSIError):
                grok_access(path)

    def test_plan_key_is_local_only_despite_api_key_shape(self):
        access = {'minimax-subscription': 'synthetic-plan-key'}
        validate_provider_access(access)
        with self.assertRaises(OpenRSIError):
            encode_provider_access(access)
        for provider in ('minimax-subscription', 'grok-subscription'):
            with self.assertRaises(OpenRSIError):
                require_remote_models([{'provider': provider}])
        with temporary_environment(access) as (env_file, environment):
            self.assertIn('TESTBED_MINIMAX_CODING_PLAN_KEY=', env_file.read_text())
            self.assertNotIn('synthetic-plan-key', json.dumps(environment))

    def test_login_file_inside_source_rejected_before_read(self):
        with tempfile.TemporaryDirectory() as folder:
            args = build_parser()[0].parse_args(['local', 'run', folder, '--dungeness', '.',
                                                '--grok-auth-file', folder + '/auth.json'])
            with self.assertRaisesRegex(OpenRSIError, 'outside'):
                credential_input(args, {'grok-subscription'})
