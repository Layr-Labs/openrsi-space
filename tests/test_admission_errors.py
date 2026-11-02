import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from catalyst.remote import fetch, HTTPFailure


class EvidenceDiagnosticTests(unittest.TestCase):
    def test_evidence_upload_uses_longer_timeout_without_changing_polling(self):
        from catalyst.client import transport
        with patch.object(transport,'fetch',return_value=b'{}') as request:
            transport.solver_fetch('https://example.invalid','/local-evidence','synthetic-session',document={})
            self.assertEqual(request.call_args.kwargs['timeout'],180)
            transport.solver_fetch('https://example.invalid','/evaluations/id','synthetic-session')
            self.assertNotIn('timeout',request.call_args.kwargs)

    def test_upload_findings_are_safe_and_scanner_outage_remains_retryable(self):
        error = HTTPFailure(400,{'code':'local_evidence_not_private','evidence_findings':[
            {'event_index':7,'rule':'embedded-credential','line':1,'value':'private'},
            {'event_index':True,'rule':'embedded-credential','line':1},
            {'event_index':8,'rule':'private','line':1}]})
        self.assertEqual(error.details['evidence_findings'],
                         [{'event_index':7,'rule':'embedded-credential','line':1}])
        self.assertNotIn('private',str(error).replace('local_evidence_not_private',''))
        self.assertNotIn('preserved',str(error))
        error.before_evaluation = True
        self.assertIn('before evaluation submission',str(error))
        unavailable = HTTPFailure(503,{'code':'credential_scanner_unavailable','retry_after_seconds':30})
        self.assertEqual(unavailable.details['retry_after_seconds'],30)
        self.assertIn('unchanged',str(unavailable))

    def test_evidence_field_survives_sanitization(self):
        details = {'code': 'local_evidence_required', 'stage': 'creation', 'field': 'local_evidence'}
        self.assertEqual(HTTPFailure(403, details).details['field'], 'local_evidence')
        self.assertNotIn('field', HTTPFailure(403, {**details, 'field': 'untrusted-field'}).details)

class AdmissionErrorTests(unittest.TestCase):
    def test_source_findings_survive_without_paths_values_or_unknown_rules(self):
        finding = {'file_index': 2, 'line': 19, 'rule': 'possible-credential',
                   'path': 'private-token', 'value': 'private-token'}
        error = HTTPFailure(400, {'code': 'source_not_publishable', 'source_findings': [
            finding, {'file_index': True, 'line': 19, 'rule': 'possible-credential'},
            {'file_index': 2, 'line': 19, 'rule': 'private-token'}, None]})
        self.assertEqual(error.details['source_findings'],
                         [{'file_index': 2, 'line': 19, 'rule': 'possible-credential'}])
        self.assertIn('zero-based', str(error))
        self.assertNotIn('private-token', str(error))
        self.assertNotIn('source_findings', HTTPFailure(400, {'code': 'source_not_publishable',
                                                           'source_findings': 'private-token'}).details)

    def test_http_error_displays_only_safe_structured_fields(self):
        body = {'error': 'private-token-do-not-print', 'code': 'daily_quota', 'scope': 'account',
                'limit': 10, 'current': 10, 'retry_after_seconds': 420, 'debug': 'private-token-do-not-print'}
        error = HTTPError('https://example.invalid/evaluations', 429, 'busy', {}, io.BytesIO(json.dumps(body).encode()))
        with patch('catalyst.remote.urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect = error
            with self.assertRaises(HTTPFailure) as raised: fetch('https://example.invalid/evaluations', 'private-token')
        self.assertIn('daily_quota', str(raised.exception))
        self.assertIn('retry_after_seconds=420', str(raised.exception))
        self.assertNotIn('saved request', str(raised.exception))
        raised.exception.saved_request_id = 'ec0dd72e-f01d-4d43-8007-747575cf550f'
        self.assertIn('same saved request ID', str(raised.exception))
        self.assertNotIn('private-token', str(raised.exception))
        self.assertEqual(raised.exception.details['limit'], 10)

    def test_malformed_and_unknown_error_details_cannot_leak_or_crash(self):
        for body in (None, [], {'code': []}, {'code': 'secret-new-code'},
                     {'code': 'account_concurrency', 'scope': [], 'limit': 'secret', 'current': True,
                      'retry_after_seconds': 'private-token'}):
            error = HTTPFailure(429, body)
            self.assertNotIn('secret', str(error))
            self.assertNotIn('private-token', str(error))
        for code in ('account_concurrency','global_capacity','submission_rate_limit','daily_quota'):
            self.assertIn(code, str(HTTPFailure(429, {'code': code, 'limit': 1, 'current': 1})))

    def test_400_keeps_safe_diagnostics_and_ignores_raw_expected_and_body(self):
        rid = 'ec0dd72e-f01d-4d43-8007-747575cf550f'
        cid = 'b091bf85-75bb-4c09-a71a-0d38cbab5e7a'
        body = {'code':'submission_validation_rejected','stage':'validation',
                'field':'evaluation.limits.max_seconds','reason':'time_limit',
                'expected':'private-token-do-not-print','error':'private-token-do-not-print',
                'request_id':rid,'correlation_id':cid}
        error = HTTPError('https://example.invalid/evaluations',400,'bad',{},io.BytesIO(json.dumps(body).encode()))
        with patch('catalyst.remote.urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect=error
            with self.assertRaises(HTTPFailure) as raised: fetch('https://example.invalid/evaluations','private-token')
        self.assertEqual(raised.exception.details['field'],'evaluation.limits.max_seconds')
        self.assertEqual(raised.exception.details['expected'],'A positive integer max_seconds.')
        self.assertIn(cid,str(raised.exception));self.assertIn(rid,str(raised.exception))
        self.assertNotIn('private-token',str(raised.exception))
        self.assertNotIn('Retry the same',str(raised.exception))

    def test_non_json_oversized_and_malicious_fields_keep_only_valid_correlation(self):
        cid='b091bf85-75bb-4c09-a71a-0d38cbab5e7a'
        for body in (b'<html>private-token</html>',b'x'*9000,
                     json.dumps({'code':'private-token','stage':[],'field':'private-token',
                                 'request_id':'private-token','reason':'private-token'}).encode()):
            error=HTTPError('https://example.invalid/evaluations',400,'bad',
                            {'X-Catalyst-Correlation-ID':cid},io.BytesIO(body))
            with patch('catalyst.remote.urllib.request.build_opener') as opener:
                opener.return_value.open.side_effect=error
                with self.assertRaises(HTTPFailure) as raised:fetch('https://example.invalid/evaluations','private-token')
            self.assertEqual(raised.exception.details,{'correlation_id':cid})
            self.assertNotIn('private-token',str(raised.exception))

    def test_edge_generated_error_id_is_saved_without_body_or_headers(self):
        eid='a'*32
        error=HTTPError('https://example.invalid/evaluations',413,'too large',
                        {'X-Catalyst-Edge-ID':eid,'Authorization':'private-token'},io.BytesIO(b'<html>private-token</html>'))
        with patch('catalyst.remote.urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect=error
            with self.assertRaises(HTTPFailure) as raised:fetch('https://example.invalid/evaluations','private-token')
        self.assertEqual(raised.exception.details,{'edge_id':eid})
        self.assertNotIn('private-token',str(raised.exception))

    def test_malicious_expected_value_is_not_retained(self):
        error=HTTPFailure(400,{'expected_protocol':'private-token','expected_evidence_mode':'private-token',
                              'expected_problem_set_digest':'private-token','edge_id':'private-token'})
        self.assertEqual(error.details,{})
