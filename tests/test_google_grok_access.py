"""New local routes preserve the funded OpenRouter boundary and old records."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from openrsi_space.common import OpenRSIError
from openrsi_space.credentials import (validate_provider_access, provider_environment,
    require_active_models, require_remote_models, encode_provider_access)
from openrsi_space.contracts.accounting import pricing_schedule, model_prices, base_pricing_schedule
from openrsi_space.contracts.model_registry import model_binding
from openrsi_space.contracts.model_equivalence import public_policy
from openrsi_space.integrations.dungeness.local import temporary_environment, credential_input
from openrsi_space.integrations.dungeness.agent import model_profile
from openrsi_space.client.model_preflight import check
from openrsi_space.compatibility import FUNDING_PROTOCOL
from openrsi_space.cli import build_parser


class GoogleGrokAccessTests(unittest.TestCase):
    def test_native_credentials_are_private_and_vertex_never_leaves_host(self):
        vertex = dict(access_token='synthetic-vertex-token',
                      expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
                      project_id='test-project')
        access = {'google': 'synthetic-google-key', 'xai': 'synthetic-xai-key', 'google-vertex': vertex}
        validate_provider_access(access)
        with temporary_environment(access) as (env, exported):
            self.assertEqual(env.stat().st_mode & 0o777, 0o600)
            for provider, value in access.items():
                for name, secret in provider_environment(provider,value).items():
                    self.assertIn(name+'='+secret, env.read_text())
                    self.assertNotIn(secret, json.dumps(exported))
        self.assertFalse(env.exists())
        with self.assertRaises(OpenRSIError):
            encode_provider_access({'google-vertex': vertex})
        with self.assertRaisesRegex(OpenRSIError,'local-only'):
            require_remote_models([{'provider':'google-vertex'}])
        for change in ({'refresh_token':'never-export'}, {'project_id':'bad/project'},
                       {'project_id':'a'*31}, {'expires_at':'2000-01-01T00:00:00Z'}):
            with self.subTest(change=change), self.assertRaises(OpenRSIError):
                validate_provider_access({'google-vertex':{**vertex,**change}})
        args=build_parser()[0].parse_args(['local','run','fixture','--provider-token-env','KEY'])
        with self.assertRaisesRegex(OpenRSIError,'API-key'):
            credential_input(args,{'google-vertex'})

    def test_profiles_select_native_protocol_and_require_runtime_support(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'runtime-contract.json').write_text(json.dumps({'schema_version':1,'runtime':'dungeness',
                'capabilities':['google-native-protocol-v1']}))
            with patch('openrsi_space.integrations.dungeness.providers.model_providers',
                       return_value={'google','google-vertex','xai'}):
                for provider, name, protocol in [('google','gemini-4-carbon','google-genai'),
                         ('google-vertex','gemini-4-neon','google-genai'), ('xai','grok-4.7','openai-responses')]:
                    self.assertEqual(model_profile(root,name,provider,pricing_schedule())['api'],protocol)
                (root/'runtime-contract.json').write_text(json.dumps({'schema_version':1,'runtime':'dungeness','capabilities':[]}))
                with self.assertRaisesRegex(OpenRSIError,'google-native-protocol-v1'):
                    model_profile(root,'gemini-4-carbon','google',pricing_schedule())

    def test_preflight_maps_exact_model_effort_and_rejects_old_server_before_work(self):
        policy={'protocol':FUNDING_PROTOCOL,'enabled':True,'providers':['openrouter'],
                'local_evidence_models':public_policy()}
        pairs=[(p,'gemini-4-'+m,'google/gemini-4-'+m)
               for p in ('google','google-vertex') for m in ('carbon','neon','argon','hydrogen')]
        pairs += [('xai','grok-4.7','x-ai/grok-4.7')]
        for provider,name,remote_name in pairs:
            local={'provider':provider,'name':name,'reasoning_effort':'high'}
            remote={'provider':'openrouter','name':remote_name,'reasoning_effort':'high'}
            with patch('openrsi_space.client.model_preflight.transport.fetch',return_value=json.dumps(policy)):
                self.assertEqual(check([local],pricing_schedule()),[remote])
            self.assertEqual(model_binding([local]),model_binding([remote]))
            self.assertNotEqual(model_binding([local]),model_binding([{**remote,'reasoning_effort':'low'}]))
            self.assertNotEqual(model_binding([{**local,'name':name+'-latest'}]),model_binding([remote]))
            with patch('openrsi_space.client.model_preflight.transport.fetch',return_value=json.dumps(
                    {**policy,'local_evidence_models':{'equivalences':[]}})):
                with self.assertRaisesRegex(OpenRSIError,'does not currently support'):
                    check([local],pricing_schedule())

    def test_retired_routes_not_advertised_and_historical_prices_unchanged(self):
        advertised=str(public_policy())
        for provider in ('grok-subscription','minimax-subscription'):
            self.assertNotIn(provider,advertised)
            with self.assertRaisesRegex(OpenRSIError,'retired'):
                require_active_models([{'provider':provider}])
        self.assertEqual(model_binding([{'provider':'grok-subscription','name':'grok-4.7'}]),
                         model_binding([{'provider':'openrouter','name':'x-ai/grok-4.7'}]))
        original=base_pricing_schedule()['entries']
        self.assertEqual(pricing_schedule()['entries'][:len(original)],original)
        self.assertEqual(model_prices({'provider':'xai','name':'grok-4.7'})['long_context']['threshold_input_tokens'],199999)
