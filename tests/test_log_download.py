import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid
import zipfile
from catalyst.client.evaluations import RemoteClient
from catalyst.common import CatalystError

class LogDownloadTests(unittest.TestCase):
    def bundle(self, identity):
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w') as archive:
            archive.writestr('manifest.json',json.dumps({'protocol':'openrsi-harness-logs-v1',
                'evaluation_id':identity,'sanitized':True,'scoring_evidence':False,'coverage':{'complete':False}}))
            archive.writestr('harness-output.txt','untrusted output')
        return output.getvalue()

    def test_private_download_uses_existing_auth_and_checks_binding(self):
        identity=str(uuid.uuid4());client=RemoteClient.__new__(RemoteClient)
        client.base='https://evaluator.example';client.bearer='synthetic-auth'
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/'logs.zip'
            with patch('catalyst.client.transport.solver_fetch',return_value=self.bundle(identity)) as fetch:
                result=client.logs(identity,target)
            self.assertEqual(fetch.call_args.args,(client.base,f'/evaluations/{identity}/logs',client.bearer))
            self.assertEqual(target.stat().st_mode&0o777,0o600)
            self.assertNotIn('untrusted output',json.dumps(result))
            previous=target.read_bytes()
            with patch('catalyst.client.transport.solver_fetch',return_value=self.bundle(str(uuid.uuid4()))):
                with self.assertRaises(CatalystError):client.logs(identity,target)
            self.assertEqual(target.read_bytes(),previous)

if __name__=='__main__':unittest.main()
