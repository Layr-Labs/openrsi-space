"""Private evidence export uses only a selected local run's recorded events."""
import json
from unittest.mock import patch
from test_local_check import LocalCheckTests
from catalyst.client.local_evidence import bundle
from catalyst.common import CatalystError


class EvidenceExportTests(LocalCheckTests):
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
