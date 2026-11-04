import json
import unittest
from unittest.mock import patch
from openrsi_space.common import OpenRSIError
from openrsi_space.client.build_policy import policy,validate,PROTOCOL

class BuildPolicyTests(unittest.TestCase):
    def test_anonymous_bounded_projection(self):
        data={'protocol':PROTOCOL,'version':'v1','digest':'a'*64,'operator_override':False,
              'enabled_profiles':['node'],'rules':[{'host':'deb.nodesource.com','include_subdomains':False}],
              'private':'not-public'}
        with patch('openrsi_space.client.build_policy.transport.fetch',return_value=json.dumps(data).encode()) as fetch:
            result=policy('https://example.test')
        fetch.assert_called_once_with('https://example.test/public/build-policy',None,limit=65536)
        self.assertNotIn('private',result)
        data['rules'][0]['host']='host\ncontrol'
        with self.assertRaises(OpenRSIError):validate(data)
