"""Authenticated allowance preflight; no model calls or real server requests."""
import copy
from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from openrsi_space.common import OpenRSIError
from openrsi_space.client.evaluations import RemoteClient
from openrsi_space.client.local_check import request_identity


class FundingPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp=self.enterContext(tempfile.TemporaryDirectory())
        self.client=RemoteClient.__new__(RemoteClient)
        self.client.state=Path(self.temp);self.client.base='https://verifier.example.test';self.client.bearer='synthetic-key'
        self.body={'protocol':'fixture','source':{'digest':'a'*64},
            'evaluation':{'model':{'provider':'openrouter','name':'openai/gpt-6-astra'},
                          'llm_access':{'grant_id':'grant_platform_funded'},'max_model_credits':2},
            'problem_set':[],'publication':{},'evidence_mode':'remote','judge':{},'context':{}}
        self.events=[];self.remaining=2;self.failure=None
        self.enterContext(patch.dict('os.environ',{'GITHUB_ACTIONS':''}))
        self.enterContext(patch('openrsi_space.client.evaluations.request_body',side_effect=lambda *a,**k:copy.deepcopy(self.body)))
        self.enterContext(patch('openrsi_space.client.evaluations.validate_evaluation_config'))
        def attach(client,body,check):
            self.events.append('upload');body['local_evidence']='b'*64
        self.upload=self.enterContext(patch('openrsi_space.client.local_evidence.attach',side_effect=attach))
        self.requests=[]
        def fetch(base,route,bearer,**kwargs):
            self.assertEqual(base,self.client.base);self.assertEqual(bearer,'synthetic-key')
            self.events.append(route)
            if route=='/funding':
                if self.failure:raise self.failure
                return json.dumps({'mode':'platform','halted':False,
                                   'allowance':{'unit':'usd_equivalent','remaining':self.remaining}}).encode()
            self.assertEqual(route,'/evaluations')
            self.requests.append(kwargs['document'])
            return json.dumps({'evaluation_id':'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee',
                               'request_id':kwargs['document']['request_id']}).encode()
        self.fetch=self.enterContext(patch('openrsi_space.client.transport.solver_fetch',side_effect=fetch))
        self.stderr=self.enterContext(redirect_stderr(io.StringIO()))

    def test_exact_remaining_amount_passes_before_upload(self):
        self.client.submit(Path(self.temp))
        self.assertEqual(self.events,['/funding','upload','/evaluations'])
        self.assertIn('requested $2; available $2',self.stderr.getvalue())

    def test_insufficient_allowance_rejects_before_upload_or_pending_request(self):
        self.remaining=1.73
        with self.assertRaisesRegex(OpenRSIError,r'\$2.*\$1.73'):
            self.client.submit(Path(self.temp))
        self.assertEqual(self.events,['/funding'])
        self.upload.assert_not_called()
        self.assertFalse((self.client.state/'remote/pending').exists())

    def test_zero_balance_and_decimal_boundary(self):
        for remaining in (0,1.999999):
            self.remaining=remaining
            with self.assertRaisesRegex(OpenRSIError,'exceeds'):self.client.submit(Path(self.temp))
        self.body['evaluation']['max_model_credits']=1.3;self.remaining=1.3
        self.client.submit(Path(self.temp))

    def test_budget_below_one_is_rejected_before_network(self):
        for cap in (0.5,0.9999999):
            self.body['evaluation']['max_model_credits']=cap
            with self.assertRaisesRegex(OpenRSIError,'Budget too low'):self.client.submit(Path(self.temp))
        self.fetch.assert_not_called();self.upload.assert_not_called()
        self.body['evaluation']['max_model_credits']=1;self.remaining=1
        self.client.submit(Path(self.temp))

    def test_invalid_allowance_fails_closed(self):
        for value in (None,True,'2',-1,float('nan'),float('inf')):
            self.remaining=value
            with self.subTest(value=value),self.assertRaisesRegex(OpenRSIError,'valid account funding allowance'):
                self.client.submit(Path(self.temp))
        self.upload.assert_not_called()

    def test_unavailable_endpoint_fails_before_upload(self):
        self.failure=OSError('synthetic connection failure')
        with self.assertRaisesRegex(OpenRSIError,'Could not check'):
            self.client.submit(Path(self.temp))
        self.upload.assert_not_called()

    def test_paused_funding_and_missing_allowance(self):
        for data,message in (({'mode':'platform','halted':True,'allowance':None},'paused'),
                             ({'mode':'platform','halted':False,'allowance':None},'valid account funding allowance'),
                             ({},'valid account funding allowance')):
            with patch('openrsi_space.client.transport.solver_fetch',return_value=json.dumps(data).encode()):
                with self.assertRaisesRegex(OpenRSIError,message):self.client.submit(Path(self.temp))
        self.upload.assert_not_called()

    def test_saved_retry_preserves_id_even_if_its_hold_consumed_allowance(self):
        first=self.client.submit(Path(self.temp))
        self.remaining=0;self.events.clear()
        # An explicit local record still yields 'passed', not 'resuming'. Recovery
        # must recognize the saved request independently of this flag.
        second=self.client.submit(Path(self.temp),local_check={
            'status':'passed','request_identity':request_identity(self.body)})
        self.assertEqual(first['request_id'],second['request_id'])
        self.assertEqual(self.events,['upload','/evaluations'])
        self.assertIn('Resuming a saved request',self.stderr.getvalue())

    def test_changed_budget_or_endpoint_is_not_treated_as_retry(self):
        self.client.submit(Path(self.temp));self.remaining=0
        self.body['evaluation']['max_model_credits']=3
        with self.assertRaisesRegex(OpenRSIError,'exceeds'):self.client.submit(Path(self.temp))
        self.body['evaluation']['max_model_credits']=2
        self.client.base='https://other.example.test'
        with self.assertRaisesRegex(OpenRSIError,'exceeds'):self.client.submit(Path(self.temp))

    def test_corrupt_saved_state_does_not_disable_funding_check(self):
        folder=self.client.state/'remote/pending';folder.mkdir(parents=True)
        for index,value in enumerate(([],None,'not-an-object',{'request_id':'wrong'})):
            (folder/f'{index}.json').write_text(json.dumps(value))
        self.remaining=0
        with self.assertRaisesRegex(OpenRSIError,'exceeds'):self.client.submit(Path(self.temp))
        self.assertEqual(self.events,['/funding'])

    def test_server_rejection_after_successful_preflight_is_preserved(self):
        # A competing submission can use capacity after the advisory snapshot.
        original=self.fetch.side_effect
        def race(base,route,bearer,**kwargs):
            if route=='/evaluations':raise OpenRSIError('server rejected raced reservation')
            return original(base,route,bearer,**kwargs)
        self.fetch.side_effect=race
        with self.assertRaisesRegex(OpenRSIError,'server rejected'):self.client.submit(Path(self.temp))
        self.assertTrue(list((self.client.state/'remote/pending').glob('*.json')))

if __name__=='__main__':unittest.main()
