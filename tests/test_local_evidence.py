"""Private evidence export uses only a selected local run's recorded events."""
import json
from unittest.mock import patch
from test_local_check import LocalCheckTests
from catalyst.client.local_evidence import bundle
from catalyst.common import CatalystError


class EvidenceExportTests(LocalCheckTests):
    def test_old_skipped_decision_cannot_omit_evidence_upload(self):
        from catalyst.client.local_evidence import attach
        from unittest.mock import Mock
        with patch('catalyst.client.transport.solver_fetch') as network:
            with self.assertRaisesRegex(CatalystError, 'no local evidence'):
                attach(Mock(), self.body, {'status': 'skipped'})
            network.assert_not_called()

    def test_subscription_export_keeps_local_identity_for_funded_equivalent(self):
        self.record['data']['model'] = {'provider': 'openai-chatgpt', 'request_model': 'gpt-6-astra',
                                         'defaults': {'reasoning_effort': 'high'}}
        self.record['data']['configuration']['repository'] = {'commit': '1'*40}
        self.body['evaluation'].update(model={'provider': 'openrouter', 'name': 'openai/gpt-6-astra',
                                              'reasoning_effort': 'high'}, max_model_credits=10)
        self.event.update(sequence=3, request_id='req-1')
        self.event['data'].update(provider='openai-chatgpt', model='gpt-6-astra', normalized_usd=10,
                                  billed_usd=0)
        self.save()
        exported = bundle(self.path, self.body)
        self.assertEqual(exported['models'], [{'provider': 'openai-chatgpt', 'name': 'gpt-6-astra',
                                               'reasoning_effort': 'high'}])
        self.assertEqual(exported['events'][0]['data']['provider'], 'openai-chatgpt')
        self.body['evaluation']['max_model_credits'] = 10.000001
        self.assertEqual(bundle(self.path, self.body)['models'], exported['models'])
        self.body['evaluation']['model']['reasoning_effort'] = 'medium'
        with self.assertRaisesRegex(ValueError, 'reasoning'):
            bundle(self.path, self.body)

    def test_exports_only_same_run_known_events_with_model_payloads(self):
        self.record['data']['configuration']['repository']={'commit':'1'*40}
        self.event['data']['normalized_usd']=100
        self.save()
        events=[{**self.event,'sequence':3,'request_id':'req-1'},
                {**self.event,'run_id':'other-run','sequence':4},
                {'run_id':'local-test','kind':'private.env','data':{'value':'DO-NOT-UPLOAD'},'sequence':5}]
        (self.path.parent/'usage/events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
        result=bundle(self.path,self.body)
        self.assertEqual(len(result['events']),1)
        self.assertNotIn('DO-NOT-UPLOAD',json.dumps(result))
        self.assertEqual(result['events'][0]['sequence'],3)

    def test_changed_source_cannot_export_as_matching_readiness(self):
        self.save();self.body['source']['digest']='b'*64
        with self.assertRaises(ValueError):bundle(self.path,self.body)

    def test_openrouter_export_preserves_charge_without_matching_remote_budget(self):
        model = {'provider': 'openrouter', 'name': 'example/model'}
        self.body['evaluation'].update(model=model, max_model_credits=20)
        self.record['data']['model'] = {'provider': 'openrouter', 'request_model': model['name']}
        self.record['data']['configuration']['repository'] = {'commit': '1'*40}
        self.event.update(sequence=3, request_id='req-1')
        self.event['data'].update(provider='openrouter', model=model['name'], normalized_usd=100,
                                  billed_usd=19.999999, billing_source='openrouter_usage', upstream_request_id='gen-one')
        self.save()
        exported = bundle(self.path, self.body)
        self.assertEqual(exported['events'][0]['data']['billed_usd'], 19.999999)
        self.event['data']['billed_usd'] = 20
        self.save()
        exported = bundle(self.path, self.body)
        self.assertEqual(exported['events'][0]['data']['billed_usd'], 20)
        del self.event['data']['billing_source']
        self.save()
        with self.assertRaisesRegex(CatalystError, 'provider-reported cost'):
            bundle(self.path, self.body)

    def test_private_bundle_limit_includes_envelope_and_rejects_overflow(self):
        from catalyst.client.local_evidence import MAX_BYTES
        from catalyst.common import canonical
        self.assertEqual(MAX_BYTES, 192 * 1024 * 1024)
        self.record['data']['configuration']['repository'] = {'commit': '1'*40}
        self.event['data']['normalized_usd'] = 100
        self.save()
        size = len(canonical(bundle(self.path, self.body)))
        with patch('catalyst.client.local_evidence.MAX_BYTES', size):
            self.assertEqual(len(canonical(bundle(self.path, self.body))), size)
        with patch('catalyst.client.local_evidence.MAX_BYTES', size - 1):
            with self.assertRaisesRegex(CatalystError, '192 MiB'):
                bundle(self.path, self.body)
