import copy
import json
from pathlib import Path
import unittest
from decimal import Decimal
from unittest.mock import patch

from openrsi_space.common import OpenRSIError
from openrsi_space.compatibility import FUNDING_PROTOCOL
from openrsi_space.contracts.accounting import credits, pricing_schedule, model_prices
from openrsi_space.contracts.model_equivalence import public_policy
from openrsi_space.contracts.model_registry import MODELS, BY_ROUTE, model_binding, reference_pricing
from openrsi_space.client.model_preflight import check


def policy():
    return dict(protocol=FUNDING_PROTOCOL, enabled=True, providers=['openrouter'],
                model_selection='solver', local_evidence_models=public_policy())


class ModelRegistryTests(unittest.TestCase):
    def test_gpt_catalog_preflight_and_version_effort_isolation(self):
        from openrsi_space.contracts.evaluation import validate_model
        names = ('gpt-6.2-astra', 'gpt-6.2-sol', 'gpt-6.1-sol', 'gpt-6.1-terra',
                 'gpt-6-astra', 'gpt-6-sol', 'gpt-6-luna', 'gpt-5.6-sol',
                 'gpt-5.6-terra', 'gpt-5.6-luna')
        no_reasoning = {'gpt-6.1-terra', 'gpt-6-sol', 'gpt-6-luna',
                        'gpt-5.6-sol', 'gpt-5.6-terra', 'gpt-5.6-luna'}
        for name in names:
            remote = dict(provider='openrouter', name='openai/' + name, reasoning_effort='high')
            for provider in ('openai-chatgpt', 'openai'):
                local = dict(provider=provider, name=name, reasoning_effort='high')
                with self.subTest(name=name, provider=provider), patch(
                        'openrsi_space.client.model_preflight.transport.fetch', return_value=json.dumps(policy())):
                    self.assertEqual(check([local], pricing_schedule()), [remote])
                    for effort in ('low', 'medium', 'high', 'xhigh', 'max'):
                        validate_model({**local, 'reasoning_effort': effort})
                    for model in (local, remote):
                        if name in no_reasoning:
                            validate_model({**model, 'reasoning_effort': 'none'})
                        else:
                            with self.assertRaisesRegex(OpenRSIError, 'reasoning effort'):
                                validate_model({**model, 'reasoning_effort': 'none'})
                    self.assertNotEqual(model_binding([local]), model_binding([{**remote, 'reasoning_effort': 'medium'}]))
                    self.assertNotEqual(model_binding([{**local, 'name': name + '-latest'}]), model_binding([remote]))
        self.assertNotEqual(model_binding([dict(provider='openai-chatgpt', name='gpt-5.6-terra')]),
                            model_binding([dict(provider='openrouter', name='openai/gpt-6.1-terra')]))
        for provider, name in [('other', 'gpt-5.6-terra'), ('openrouter', 'vendor/unknown')]:
            with self.assertRaisesRegex(OpenRSIError, 'reasoning effort'):
                validate_model(dict(provider=provider, name=name, reasoning_effort='none'), check_pricing=False)
        self.assertNotEqual(model_binding([dict(provider='openai-chatgpt', name='gpt-5.6-terra', reasoning_effort='none')]),
                            model_binding([dict(provider='openrouter', name='openai/gpt-5.6-terra')]))

    def test_terra_cache_and_long_context_prices(self):
        for provider in ('openai', 'openai-chatgpt', 'openrouter'):
            model = dict(provider=provider, name=('openai/' if provider == 'openrouter' else '') + 'gpt-5.6-terra')
            usage = dict(input_tokens=272000, output_tokens=1000, cached_read_tokens=20000, cache_write_tokens=10000)
            self.assertEqual(credits(usage, model), Decimal('0.525'))
            self.assertEqual(credits({**usage, 'input_tokens':272001}, model), Decimal('1.044004'))

    def test_sonnet_and_haiku_preflight_and_exact_model_bindings(self):
        for family in ('sonnet', 'haiku'):
            remote = dict(provider='openrouter', name=f'anthropic/claude-{family}-5.5', reasoning_effort='high')
            for provider in ('claude-subscription', 'anthropic'):
                local = dict(provider=provider, name=f'claude-{family}-5-5', reasoning_effort='high')
                with self.subTest(family=family, provider=provider), patch(
                        'openrsi_space.client.model_preflight.transport.fetch', return_value=json.dumps(policy())):
                    self.assertEqual(check([local], pricing_schedule()), [remote])
                    self.assertEqual(model_binding([local]), model_binding([remote]))
                    for field, value in [('name', f'anthropic/claude-{family}-4.5'),
                                         ('reasoning_effort', 'low')]:
                        self.assertNotEqual(model_binding([local]), model_binding([{**remote, field: value}]))

    def test_sonnet_and_haiku_cache_duration_and_context_accounting(self):
        for provider in ('claude-subscription', 'anthropic', 'openrouter'):
            def model(family):
                name = f'anthropic/claude-{family}-5.5' if provider == 'openrouter' else f'claude-{family}-5-5'
                return dict(provider=provider, name=name)
            # Inclusive input contains ordinary, read, 5m-write and 1h-write buckets.
            usage = dict(input_tokens=100000, output_tokens=1000, cached_read_tokens=20000,
                         cache_write_tokens=30000, cache_write_1h_tokens=10000)
            with self.subTest(provider=provider):
                self.assertEqual(credits(usage, model('sonnet')), Decimal('0.202'))
                self.assertEqual(credits(usage, model('haiku')), Decimal('0.0102'))
                # One extra ordinary input token switches every bucket to the higher tier.
                self.assertEqual(credits({**usage, 'input_tokens':100001}, model('haiku')), Decimal('0.0510005'))
                self.assertEqual(credits({**usage, 'input_tokens':99999}, model('haiku')), Decimal('0.0101999'))
                with self.assertRaisesRegex(OpenRSIError, 'Cache-duration usage is missing'):
                    credits({k:v for k,v in usage.items() if k != 'cache_write_1h_tokens'}, model('haiku'))

    def test_every_route_has_unique_identity_and_reference_price(self):
        routes = [('openrouter', m.canonical_id) for m in MODELS]
        routes += [r for m in MODELS for r in m.local_routes]
        self.assertEqual(len(routes), len(set(routes)))
        self.assertEqual(len(routes), len(BY_ROUTE))
        pricing = pricing_schedule()
        for provider, name in routes:
            with self.subTest(provider=provider, name=name):
                self.assertEqual(model_prices(dict(provider=provider, name=name), pricing)['upstream_id'], BY_ROUTE[(provider,name)].canonical_id)

    def test_fable_versions_and_effort_remain_distinct(self):
        bindings = []
        for native, routed in [('claude-fable-5', 'anthropic/claude-fable-5'),
                               ('claude-fable-5-1', 'anthropic/claude-fable-5.1'),
                               ('claude-fable-5-2', 'anthropic/claude-fable-5.2')]:
            local = dict(provider='claude-subscription', name=native, reasoning_effort='high')
            remote = dict(provider='openrouter', name=routed, reasoning_effort='high')
            self.assertEqual(model_binding([local]), model_binding([remote]))
            self.assertNotEqual(model_binding([local]), model_binding([{**remote, 'reasoning_effort':'low'}]))
            self.assertNotEqual(model_binding([{**local, 'name':native+'-latest'}]), model_binding([remote]))
            bindings.append(model_binding([local]))
        self.assertEqual(len({str(b) for b in bindings}), 3)

    def test_expansion_preserves_existing_prices_and_input(self):
        path = Path(__file__).resolve().parents[1] / 'src/openrsi_space/pricing/pricing.json'
        original = json.loads(path.read_text())
        before = copy.deepcopy(original)
        expanded = reference_pricing(original)
        self.assertEqual(original, before)
        self.assertEqual(expanded['entries'][:len(original['entries'])], original['entries'])
        self.assertEqual(reference_pricing(expanded), expanded)
        prices = model_prices(dict(provider='claude-subscription', name='claude-fable-5-2'), expanded)
        self.assertEqual([prices[k] for k in ('input_per_mtok','output_per_mtok','cached_read_per_mtok',
                                             'cache_write_per_mtok','cache_write_1h_per_mtok')], [8,40,.2,10,16])

    def test_fable_preflight_uses_public_policy_without_authentication(self):
        local = dict(provider='claude-subscription', name='claude-fable-5-2', reasoning_effort='high')
        with patch('openrsi_space.client.model_preflight.transport.fetch', return_value=json.dumps(policy())) as fetch:
            remote = check([local], pricing_schedule())
        self.assertEqual(remote, [dict(provider='openrouter',name='anthropic/claude-fable-5.2',reasoning_effort='high')])
        self.assertIsNone(fetch.call_args.args[1])
        self.assertTrue(fetch.call_args.args[0].endswith('/public/funding-policy'))

    def test_old_server_policy_blocks_before_local_work(self):
        response = policy()
        response['local_evidence_models']['equivalences'] = []
        with patch('openrsi_space.client.model_preflight.transport.fetch', return_value=json.dumps(response)):
            with self.assertRaisesRegex(OpenRSIError, 'does not currently support'):
                check([dict(provider='claude-subscription',name='claude-fable-5-2')],pricing_schedule())
            # Same exact OpenRouter route remains supported without an alias entry.
            check([dict(provider='openrouter',name='anthropic/claude-fable-5.2')],pricing_schedule())

    def test_unknown_pair_and_missing_price_fail_without_network(self):
        with patch('openrsi_space.client.model_preflight.transport.fetch') as fetch:
            with self.assertRaisesRegex(OpenRSIError, 'No supported remote equivalent'):
                check([dict(provider='claude-subscription',name='claude-fable-latest')],pricing_schedule())
            with self.assertRaisesRegex(OpenRSIError, 'no reference pricing'):
                check([dict(provider='claude-subscription',name='claude-fable-5-2')],{'entries':[]})
            fetch.assert_not_called()

    def test_unavailable_restricted_and_malformed_policy_fail_closed(self):
        for response in [[], {}, {**policy(),'enabled':False},
                         {**policy(),'model_selection':'restricted','models':[]}]:
            with self.subTest(policy=response), patch('openrsi_space.client.model_preflight.transport.fetch',return_value=json.dumps(response)):
                with self.assertRaises(OpenRSIError):
                    check([dict(provider='claude-subscription',name='claude-fable-5-2')],pricing_schedule())
