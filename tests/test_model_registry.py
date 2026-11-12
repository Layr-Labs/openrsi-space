import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from openrsi_space.common import OpenRSIError
from openrsi_space.compatibility import FUNDING_PROTOCOL
from openrsi_space.contracts.accounting import pricing_schedule, model_prices
from openrsi_space.contracts.model_equivalence import public_policy
from openrsi_space.contracts.model_registry import MODELS, BY_ROUTE, model_binding, reference_pricing
from openrsi_space.client.model_preflight import check


def policy():
    return dict(protocol=FUNDING_PROTOCOL, enabled=True, providers=['openrouter'],
                model_selection='solver', local_evidence_models=public_policy())


class ModelRegistryTests(unittest.TestCase):
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
