"""Source-size checks need neither model credentials nor an upload."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from catalyst.common import CatalystError, make_bundle
from catalyst.client.source_limits import check, measure, policy
from catalyst.client.transport import HTTPFailure
from catalyst.cli import main


class SourceLimitsTests(unittest.TestCase):
    def test_measure_counts_expanded_files_not_zip_or_snapshot_metadata(self):
        files = {'harness.json': json.dumps({'schema_version': 1, 'kind': 'harness', 'id': 'fixture', 'title': 'Fixture',
                 'execution': {'interface': 'catalyst-exec-v1', 'dockerfile': 'Dockerfile', 'entrypoint': ['python3', '/agent.py']}}).encode(),
                 'Dockerfile': b'FROM python:3.12-slim\nCOPY agent.py /agent.py\n',
                 'agent.py': b'# generic research loop\n'*1000}
        snapshot, archive = make_bundle(files)
        size = measure(snapshot, archive)
        self.assertEqual(size['expanded_source_bytes'], sum(map(len, files.values())))
        self.assertLess(size['archive_bytes'], size['expanded_source_bytes'])
        with self.assertRaisesRegex(CatalystError, 'ZIP compression does not change'):
            check(size, 1000, 8*1024*1024)
        check(size, 8*1024*1024, 8*1024*1024)

    def test_policy_is_anonymous_bounded_and_ignores_unknown_text(self):
        document = {'protocol': 'catalyst-submission-policy-v1', 'max_expanded_source_bytes': 8388608,
                    'max_archive_bytes': 8388608, 'unexpected': 'private-canary'}
        with patch('catalyst.client.source_limits.transport.fetch', return_value=json.dumps(document)) as fetch:
            result = policy('https://example.test')
        self.assertNotIn('private-canary', json.dumps(result))
        fetch.assert_called_once_with('https://example.test/public/submission-policy', None, limit=8192)
        for value in (True, -1, '8388608', 2**40):
            with patch('catalyst.client.source_limits.transport.fetch', return_value=json.dumps({**document, 'max_expanded_source_bytes': value})):
                with self.assertRaises(CatalystError):
                    policy('https://example.test')

    def test_limits_command_does_not_load_any_credential(self):
        document = {'protocol': 'catalyst-submission-policy-v1', 'max_expanded_source_bytes': 8388608,
                    'max_archive_bytes': 8388608}
        with patch('catalyst.client.source_limits.policy', return_value=document), \
             patch('catalyst.client.evaluations.RemoteClient', side_effect=AssertionError('No login needed')), \
             redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['remote', 'limits']), 0)
        self.assertEqual(json.loads(output.getvalue()), document)

    def test_remote_size_error_keeps_only_safe_numeric_diagnostics(self):
        error = HTTPFailure(413, {'code': 'source_package_too_large', 'stage': 'validation',
            'field': 'source.expanded_bytes', 'limit': 8388608, 'current': 9000000, 'error': 'private-canary'})
        self.assertIn('Remove unused bundled files', str(error))
        self.assertEqual(error.details['current'], 9000000)
        self.assertNotIn('private-canary', str(error))

    def test_submission_stops_locally_even_when_oversized_source_compresses_well(self):
        from harness_fixture import create_harness
        from catalyst.client.evaluations import request_body
        with tempfile.TemporaryDirectory() as folder:
            harness = Path(folder) / 'harness'
            create_harness(harness)
            (harness/'unused.py').write_bytes(b'# regular source\n' * 600000)
            with patch('catalyst.client.transport.fetch', side_effect=AssertionError('No upload')):
                with self.assertRaisesRegex(CatalystError, 'Expanded harness source'):
                    request_body(harness, 'https://verifier.example.test')
