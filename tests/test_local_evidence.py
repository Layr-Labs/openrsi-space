"""Private evidence export uses only a selected local run's recorded events."""
import json
from unittest.mock import patch
from test_local_check import LocalCheckTests
from openrsi_space.client.local_evidence import bundle
from openrsi_space.common import OpenRSIError


class EvidenceExportTests(LocalCheckTests):
    def rejection_trace(self):
        from copy import deepcopy
        self.record['data']['configuration']['repository'] = {'commit': '1'*40}
        self.record['data']['usage']['model_requests'] = 2
        self.save()
        success = self.exchanges(self.event)
        failed = deepcopy(success)
        for event in failed:
            event['request_id'] = 'rejected-call'
            event['sequence'] += 3
        failed[1]['data'].update(status='provider_error', response={
            'type': 'error', 'error': {'type': 'rate_limit_error', 'message': 'Try later.'}})
        failed[2]['data'].update(status='provider_error', total_tokens=0, normalized_usd=0)
        return success + failed

    def test_export_keeps_settled_rejections_and_successful_exchanges(self):
        events = self.rejection_trace()
        log = self.path.parent / 'usage/events.jsonl'
        for tokens, spent in ((0, 0), (10, .01)):
            events[-1]['data'].update(total_tokens=tokens, normalized_usd=spent)
            log.write_text(''.join(json.dumps(e)+'\n' for e in events))
            exported = bundle(self.path, self.body)
            self.assertEqual(len(exported['events']), 6)
            self.assertEqual(exported['events'][-1]['data']['status'], 'provider_error')
            self.assertEqual(exported['events'][-1]['data']['normalized_usd'], spent)

    def test_failed_exchange_needs_complete_settled_accounting_and_a_success(self):
        from copy import deepcopy
        from openrsi_space.contracts.local_evidence import validate_exchanges
        raw = self.rejection_trace()
        models = [{'provider': 'openai', 'name': 'gpt-5.6-sol'}]
        events = [{k:v for k,v in e.items() if k != 'run_id'} for e in raw]
        validate_exchanges(events, models)
        invalid = [events[3:], events[:-1]]
        for change in ({'accounting_method': 'unavailable'}, {'total_tokens': None},
                       {'total_tokens': -1}, {'total_tokens': True}, {'normalized_usd': None},
                       {'normalized_usd': -1}, {'normalized_usd': float('nan')}, {'status': 'unknown'}):
            bad = deepcopy(events); bad[-1]['data'].update(change); invalid.append(bad)
        bad = deepcopy(events)
        for event in bad[3:]: event['data']['model'] = 'undeclared-model'
        invalid.append(bad)
        for bad in invalid:
            with self.subTest(events=bad), self.assertRaises(OpenRSIError):
                validate_exchanges(bad, models)

    def test_export_preserves_recorded_cap_even_when_spending_and_remote_cap_are_lower(self):
        self.record['data']['configuration']['resolved']['limits']['max_usd'] = 2
        self.record['data']['configuration']['repository'] = {'commit': '1'*40}
        self.event['data']['normalized_usd'] = 1.73
        self.body['evaluation']['max_model_credits'] = 1.9
        self.save()
        self.assertEqual(bundle(self.path, self.body)['local_budget_cap_usd'], 2)

    def test_failed_upload_retains_safe_diagnostics_without_claiming_a_saved_request(self):
        from unittest.mock import Mock
        from openrsi_space.client.local_evidence import attach
        from openrsi_space.client.transport import HTTPFailure
        client=Mock(state=self.state,base='https://example.invalid',bearer='private-token')
        failure=HTTPFailure(400,{'code':'local_evidence_not_private',
            'evidence_findings':[{'event_index':0,'line':1,'rule':'embedded-credential','value':'private-token'}]})
        with patch('openrsi_space.client.local_evidence.bundle',return_value={}), \
                patch('openrsi_space.client.transport.solver_fetch',side_effect=failure):
            with self.assertRaises(HTTPFailure) as error:
                attach(client,self.body,{'record_path':str(self.path)})
        self.assertIn('before evaluation submission',str(error.exception))
        self.assertNotIn('saved request',str(error.exception))
        saved=json.loads(error.exception.diagnostic_path.read_text())
        self.assertEqual(saved['operation'],'local_evidence_upload')
        self.assertIsNone(saved['request_id'])
        self.assertNotIn('private-token',json.dumps(saved))
        self.assertFalse((self.state/'remote/pending').exists())

    def test_retry_with_explicit_local_run_reuses_original_binding(self):
        from types import SimpleNamespace
        from openrsi_space.client.local_evidence import attach
        client = SimpleNamespace(state=self.state, base='https://example.invalid', bearer='synthetic')
        with patch('openrsi_space.client.local_check.pending_request', return_value={'local_evidence': 'a'*64}), \
                patch('openrsi_space.client.local_evidence.bundle') as bundle_mock, \
                patch('openrsi_space.client.transport.solver_fetch') as network:
            attach(client, self.body, {'record_path': str(self.path)})
        self.assertEqual(self.body['local_evidence'], 'a'*64)
        bundle_mock.assert_not_called()
        network.assert_not_called()

    def test_lookup_reuses_uploaded_bundle_after_lost_response_or_changed_budget(self):
        from types import SimpleNamespace
        from openrsi_space.client.local_evidence import attach
        from openrsi_space.contracts.results import digest
        from openrsi_space.client.transport import HTTPFailure
        client = SimpleNamespace(state=self.state, base='https://example.invalid', bearer='synthetic')
        doc = {'synthetic': True}
        binding = {'protocol': 'catalyst-local-evidence-v1', 'digest': digest(doc), 'private': True}
        for exists in (True, False):
            calls = []
            def fetch(base, route, bearer, **kwargs):
                calls.append((route, kwargs))
                if route.endswith('/'+digest(doc)) and not exists:
                    raise HTTPFailure(404)
                return json.dumps(binding).encode()
            with patch('openrsi_space.client.local_evidence.bundle', return_value=doc), \
                    patch('openrsi_space.client.transport.solver_fetch', side_effect=fetch):
                attach(client, self.body, {'record_path': str(self.path)})
            self.assertEqual(len(calls), 1 if exists else 2)
            self.assertEqual(calls[0][1], {})
            self.assertEqual(self.body['local_evidence'], digest(doc))

    def test_old_skipped_decision_cannot_omit_evidence_upload(self):
        from openrsi_space.client.local_evidence import attach
        from unittest.mock import Mock
        with patch('openrsi_space.client.transport.solver_fetch') as network:
            with self.assertRaisesRegex(OpenRSIError, 'no local evidence'):
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
        events=[*self.exchanges(self.event),
                {**self.event,'run_id':'other-run','sequence':4},
                {'run_id':'local-test','kind':'private.env','data':{'value':'DO-NOT-UPLOAD'},'sequence':5}]
        (self.path.parent/'usage/events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
        result=bundle(self.path,self.body)
        self.assertEqual(len(result['events']),3)
        self.assertNotIn('DO-NOT-UPLOAD',json.dumps(result))
        self.assertEqual(result['events'][2]['sequence'],3)

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
        self.assertEqual(exported['events'][2]['data']['billed_usd'], 19.999999)
        self.event['data']['billed_usd'] = 20
        self.save()
        exported = bundle(self.path, self.body)
        self.assertEqual(exported['events'][2]['data']['billed_usd'], 20)
        del self.event['data']['billing_source']
        self.save()
        with self.assertRaisesRegex(OpenRSIError, 'provider-reported cost'):
            bundle(self.path, self.body)

    def test_private_bundle_limit_includes_envelope_and_rejects_overflow(self):
        from openrsi_space.client.local_evidence import MAX_BYTES
        from openrsi_space.common import canonical
        self.assertEqual(MAX_BYTES, 192 * 1024 * 1024)
        self.record['data']['configuration']['repository'] = {'commit': '1'*40}
        self.event['data']['normalized_usd'] = 100
        self.save()
        size = len(canonical(bundle(self.path, self.body)))
        with patch('openrsi_space.client.local_evidence.MAX_BYTES', size):
            self.assertEqual(len(canonical(bundle(self.path, self.body))), size)
        with patch('openrsi_space.client.local_evidence.MAX_BYTES', size - 1):
            with self.assertRaisesRegex(OpenRSIError, '192 MiB'):
                bundle(self.path, self.body)
