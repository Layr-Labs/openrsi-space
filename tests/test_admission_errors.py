import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from catalyst.remote import fetch, HTTPFailure

class AdmissionErrorTests(unittest.TestCase):
    def test_http_error_displays_only_safe_structured_fields(self):
        body = {'error': 'private-token-do-not-print', 'code': 'daily_quota', 'scope': 'account',
                'limit': 10, 'current': 10, 'retry_after_seconds': 420, 'debug': 'private-token-do-not-print'}
        error = HTTPError('https://example.invalid/evaluations', 429, 'busy', {}, io.BytesIO(json.dumps(body).encode()))
        with patch('catalyst.remote.urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect = error
            with self.assertRaises(HTTPFailure) as raised: fetch('https://example.invalid/evaluations', 'private-token')
        self.assertIn('daily_quota', str(raised.exception))
        self.assertIn('retry_after_seconds=420', str(raised.exception))
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
