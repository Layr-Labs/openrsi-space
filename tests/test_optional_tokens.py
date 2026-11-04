import copy
from pathlib import Path
import tempfile
import unittest
from openrsi_space.common import OpenRSIError
from openrsi_space.remote import evaluation_config, validate_evaluation_config, limits_within
from openrsi_space.tiers import project_observation
from harness_fixture import evaluation
from test_tiers import observation, MODEL

class OptionalTokenTests(unittest.TestCase):
 def test_null_omitted_positive_and_invalid(self):
  for tokens in (None,100):
   config=evaluation();config['limits']['max_model_tokens']=tokens
   self.assertIs(validate_evaluation_config(config),config)
  config=evaluation();del config['limits']['max_model_tokens'];validate_evaluation_config(config)
  for value in (0,-1,True,'100',1.5):
   config=evaluation();config['limits']['max_model_tokens']=value
   with self.assertRaises(OpenRSIError):validate_evaluation_config(config)
 def test_default_has_no_hidden_cap(self):
  with tempfile.TemporaryDirectory() as tmp:
   config=evaluation_config(Path(tmp)/'absent.json',{'provider':'openai','model':'gpt-5.6-sol','budget':20})
   self.assertIsNone(config['limits'].get('max_model_tokens'))
   self.assertEqual(config['limits']['max_seconds'],10800)
 def test_explicit_time_limit_and_saved_manifest_are_preserved(self):
  import json
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'evaluation.json'
   options={'provider':'openai','model':'gpt-5.6-sol','budget':20}
   self.assertEqual(evaluation_config(path,{**options,'max_seconds':60})['limits']['max_seconds'],60)
   saved=evaluation();path.write_text(json.dumps(saved))
   self.assertEqual(evaluation_config(path)['limits']['max_seconds'],900)
   self.assertEqual(evaluation_config(path,{'max_seconds':10800})['limits']['max_seconds'],10800)
   self.assertEqual(json.loads(path.read_text()),saved)
 def test_grants_distinguish_unlimited_from_finite(self):
  unlimited={'max_seconds':900}; finite={**unlimited,'max_model_tokens':100}
  self.assertTrue(limits_within(unlimited,unlimited))
  self.assertTrue(limits_within(finite,unlimited))
  self.assertFalse(limits_within(unlimited,finite))
  self.assertFalse(limits_within({**finite,'max_model_tokens':101},finite))
  self.assertFalse(limits_within({'max_seconds':901},unlimited))
  self.assertFalse(limits_within(unlimited,{}))
 def test_large_ledger_remains_valid_without_cap_but_credit_limit_still_applies(self):
  for limits in ({'max_seconds':900},{'max_seconds':900,'max_model_tokens':None}):
   result=project_observation(observation(),MODEL,500,limits)
   self.assertEqual(result['best']['performance'],600)
   with self.assertRaises(OpenRSIError):project_observation(observation(),MODEL,20,limits)
  with self.assertRaisesRegex(OpenRSIError,'token limit'):
   project_observation(observation(),MODEL,500,{'max_seconds':900,'max_model_tokens':1000000})
