from datetime import datetime, timedelta, timezone
import json
import unittest
from openrsi_space.common import OpenRSIError
from openrsi_space.credentials import validate_provider_access, encode_provider_access
from openrsi_space.integrations.dungeness.local import temporary_environment


class ClaudeAccessTests(unittest.TestCase):
    def access(self):
        return {'claude-subscription':{'access_token':'synthetic-claude-token',
                'expires_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()}}

    def test_exact_access_fields_no_refresh_and_valid_expiry(self):
        valid=self.access();validate_provider_access(valid)
        with self.assertRaisesRegex(OpenRSIError, 'API keys only'):
            encode_provider_access(valid)
        for change in ({'refresh_token':'never-transfer'}, {'expires_at':'2000-01-01T00:00:00Z'},
                       {'expires_at':'2030-01-01T00:00:00'}, {'expires_at':'2030-01-01\n00:00:00Z'},
                       {'access_token':'injected\nENV=value'}):
            with self.subTest(change=change), self.assertRaises(OpenRSIError):
                validate_provider_access({'claude-subscription':{**valid['claude-subscription'],**change}})

    def test_local_private_staging_and_cleanup(self):
        access=self.access()
        with temporary_environment(access) as (env_file, env):
            folder=env_file.parent
            self.assertEqual(env_file.stat().st_mode & 0o777,0o600)
            self.assertEqual(folder.stat().st_mode & 0o777,0o700)
            self.assertIn('TESTBED_CLAUDE_ACCESS_TOKEN=synthetic-claude-token',env_file.read_text())
            self.assertNotIn('synthetic-claude-token',json.dumps(env))
        self.assertFalse(folder.exists());self.assertEqual(access,{})
