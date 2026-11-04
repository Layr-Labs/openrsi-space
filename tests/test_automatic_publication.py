"""Client publication contracts; synthetic Yukon and no research execution."""
import base64
import copy
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout, redirect_stderr
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

from harness_fixture import create_harness
from test_yukon import completed
from openrsi_space.common import OpenRSIError, read_json, canonical
from openrsi_space.cli.parser import build_parser
from openrsi_space.client import yukon_publication as publication
from openrsi_space.contracts.yukon_publication import metadata
from openrsi_space.remote import request_body


class AutomaticPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        create_harness(self.root / 'harness')
        (self.root / 'note.md').write_text('My methodology.')
        self.owner, self.board, self.eid, self.sid, self.jid = [str(uuid.uuid4()) for _ in range(5)]
        self.cli = build_parser()[0]
        with patch.dict(os.environ, {'OPENRSI_LOCAL_TEST': '', 'OPENRSI_LOCAL_ECDSA': ''}):
            self.body = {**request_body(self.root / 'harness', 'https://verifier.example.test'),
                         'request_id': str(uuid.uuid4())}
        self.result = completed(self.body, self.eid)
        self.client = SimpleNamespace(state=self.root / 'state', base='https://verifier.example.test',
            bearer='ykn_synthetic_fixture', session=lambda _: {'request': self.body},
            status=lambda _: self.result)
        self.info = {'benchmark_id': self.board, 'harness': 'Test harness', 'note': 'Methods', 'dependencies': []}
        self.posts = []; self.lost = False; self.duplicate = False; self.upstream = 'accepted'
        self.account = self.owner
        self.sent_binding = []
        self.patches = [
            patch.object(publication.yukon, 'api_origin', return_value='https://yukon.example.test'),
            patch.object(publication.yukon, 'request', side_effect=self.request),
            patch.object(publication.transport, 'fetch', return_value=canonical({
                'protocol': publication.SESSION_PROTOCOL, 'owner_id': self.owner})),
            patch.object(publication, 'bind_job', side_effect=self.bind),
        ]
        for p in self.patches: p.start(); self.addCleanup(p.stop)

    def request(self, origin, path, token, **kw):
        self.assertEqual(origin, 'https://yukon.example.test')
        self.assertEqual(token, self.client.bearer)
        if path == '/api/me': return {'account': {'id': self.account}}
        if path == '/api/benchmarks/' + self.board:
            return {'benchmark': {'id': self.board, 'status': 'open', 'mode': 'pareto',
                                  'editablePaths': ['submission/verification.json']}}
        submission = {'id': self.sid, 'benchmarkId': self.board, 'solverAccountId': self.owner, 'status': self.upstream}
        if path.endswith('/submissions'):
            self.posts.append(kw)
            if self.lost:
                self.lost = False; self.duplicate = True
                raise publication.yukon.PublicationError(503)
            return {'submission': submission, 'job': None if self.duplicate else {'id': self.jid}}
        if path.endswith('/publication-job'): return {'job': {'id': self.jid}}
        self.assertEqual(path, '/api/submissions/' + self.sid)
        return {'submission': submission}

    def bind(self, root, job_id, board, **kw):
        self.sent_binding.append(kw)
        self.assertEqual((job_id, board), (self.jid, self.board))
        self.assertEqual(kw['reference']['evaluation_id'], self.eid)
        return {'submission_id': self.sid}

    def authorize(self):
        publication.prepare(self.client, self.body, self.info)

    def arguments(self, *extra):
        return self.cli.parse_args(['remote', 'submit', str(self.root / 'harness'), *extra])

    def test_opt_in_and_explicit_dependency_declaration_required(self):
        self.assertIsNone(publication.options(self.arguments()))
        with self.assertRaises(OpenRSIError):
            publication.options(self.arguments('--note-file', str(self.root / 'note.md')))
        with self.assertRaises(OpenRSIError):
            publication.options(self.arguments('--publish-to-yukon', '--note-file', str(self.root / 'note.md')))

    def test_title_and_existing_dependency_format(self):
        deps = [{'submissionId': str(uuid.uuid4()), 'rationale': 'Uses generic loop', 'evidence': 'agent.py'}]
        (self.root / 'deps.json').write_text(json.dumps(deps))
        result = publication.options(self.arguments('--publish-to-yukon', '--benchmark', self.board,
            '--publication-title', 'My harness', '--note-file', str(self.root / 'note.md'),
            '--dependencies-file', str(self.root / 'deps.json')))
        self.assertEqual(result['harness'], 'My harness'); self.assertEqual(result['dependencies'], deps)

    def test_preparation_saves_consent_but_no_credentials_or_upstream_submission(self):
        self.authorize()
        self.assertEqual(self.posts, [])
        path = publication.intent_path(self.client, self.body)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(self.client.bearer, path.read_text())
        with self.assertRaises(OpenRSIError):
            publication.prepare(self.client, self.body, {**self.info, 'note': 'Changed'})

    def test_receipt_only_publication_and_repeat_wait_do_not_duplicate(self):
        self.authorize()
        original = copy.deepcopy(self.result)
        self.assertEqual(publication.publish(self.client, self.eid)['state'], 'published')
        self.assertEqual(publication.publish(self.client, self.eid)['state'], 'published')
        self.assertEqual(len(self.posts), 1)
        value = read_json(publication.intent_path(self.client, self.body))
        with tarfile.open(fileobj=io.BytesIO(base64.b64decode(value['archive_base64'])), mode='r:gz') as tar:
            self.assertEqual(tar.getnames(), ['submission/verification.json'])
            self.assertEqual(json.load(tar.extractfile('submission/verification.json'))['evaluation_id'], self.eid)
        self.assertEqual(self.result, original)
        self.assertNotIn(self.client.bearer, json.dumps(value))
        self.assertEqual(self.sent_binding[0]['bearer'], self.client.bearer)

    def test_lost_response_recovers_exact_bytes_and_idempotency_key(self):
        self.authorize(); self.lost = True
        self.assertEqual(publication.publish(self.client, self.eid)['state'], 'retryable_failure')
        self.assertEqual(publication.publish(self.client, self.eid)['state'], 'published')
        self.assertEqual(self.posts[0], self.posts[1])
        self.assertEqual(len(self.sent_binding), 1)

    def test_pending_yukon_is_not_reported_as_published(self):
        self.authorize(); self.upstream = 'validating'
        self.assertEqual(publication.publish(self.client, self.eid, wait=False)['state'], 'awaiting_yukon')
        self.upstream = 'accepted'
        self.assertEqual(publication.publish(self.client, self.eid)['state'], 'published')
        self.assertEqual(len(self.posts), 1)

    def test_wrong_account_cannot_publish_or_replace_saved_intent(self):
        self.authorize(); self.account = str(uuid.uuid4())
        self.assertEqual(publication.publish(self.client, self.eid)['state'], 'needs_authentication')
        self.assertEqual(self.posts, [])
        with self.assertRaises(OpenRSIError): self.authorize()

    def test_changed_request_or_archive_stops_publication(self):
        self.authorize(); self.body['evaluation']['max_model_credits'] += 1
        with self.assertRaises(OpenRSIError): publication.publish(self.client, self.eid)
        self.assertEqual(self.posts, [])

    def test_corrupted_saved_archive_cannot_upload_other_files(self):
        self.authorize(); self.lost = True
        publication.publish(self.client, self.eid)
        path = publication.intent_path(self.client, self.body); value = read_json(path)
        value['archive_base64'] = base64.b64encode(b'arbitrary files').decode(); publication.save(path, value)
        self.assertEqual(publication.publish(self.client, self.eid)['state'], 'retryable_failure')
        self.assertEqual(len(self.posts), 1)

    def test_new_client_resumes_without_original_source_directory(self):
        self.authorize()
        other_client = SimpleNamespace(**vars(self.client))
        (self.root / 'harness' / 'harness.json').unlink()
        self.assertEqual(publication.publish(other_client, self.eid)['state'], 'published')
        self.assertEqual(len(self.posts), 1)

    def test_failed_and_running_evaluations_are_not_uploaded(self):
        self.authorize()
        self.result['status'] = 'running'
        self.assertEqual(publication.publish(self.client, self.eid)['state'], 'pending')
        self.result['status'] = 'failed'
        self.assertEqual(publication.publish(self.client, self.eid)['state'], 'not_eligible')
        self.assertEqual(self.posts, [])

    def test_yukon_failure_preserves_result_and_never_reposts(self):
        self.authorize(); self.upstream = 'failed'
        for _ in range(2):
            result = publication.publish(self.client, self.eid)
            self.assertEqual(result['error_code'], 'yukon_publication_failed')
        self.assertEqual(len(self.posts), 1)
        self.assertTrue(self.result['valid'])

    def test_read_only_status_never_publishes(self):
        self.authorize()
        self.assertEqual(publication.status(self.client, self.eid)['state'], 'pending')
        self.assertEqual(self.posts, [])
        for flags in [[], ['--retry']]:
            self.assertEqual(self.cli.parse_args(['remote', 'publication', self.eid, *flags]).id, self.eid)

    def test_remote_wait_completes_saved_publication_without_another_submit(self):
        from openrsi_space.cli.commands import main
        self.authorize()
        self.client.wait = lambda _: {'metrics': {'evidenceMode': 'remote'}, 'valid': True}
        self.client.folder = lambda _: self.root / 'retained-result'
        # No submit method or source export is provided: neither may be called.
        with patch('openrsi_space.client.evaluations.RemoteClient', return_value=self.client):
            for _ in range(2):
                output = io.StringIO()
                with redirect_stdout(output), redirect_stderr(io.StringIO()):
                    code = main(['remote', 'wait', self.eid])
                self.assertEqual(code, 0)
                self.assertEqual(json.loads(output.getvalue())['publication']['state'], 'published')
        self.assertEqual(len(self.posts), 1)

    def test_exact_login_key_cannot_be_copied_into_public_note(self):
        with self.assertRaises(OpenRSIError):
            publication.prepare(self.client, self.body, {**self.info, 'note': self.client.bearer})
        self.assertFalse(publication.intent_path(self.client, self.body).exists())

    def test_cli_publication_failure_is_nonzero_without_losing_verified_result(self):
        from openrsi_space.cli.commands import main
        self.authorize(); self.upstream = 'failed'
        self.client.wait = lambda _: {'metrics': {'evidenceMode': 'remote'}, 'valid': True}
        self.client.folder = lambda _: self.root / 'retained-result'
        output, errors = io.StringIO(), io.StringIO()
        with patch('openrsi_space.client.evaluations.RemoteClient', return_value=self.client), \
                redirect_stdout(output), redirect_stderr(errors):
            code = main(['remote', 'wait', self.eid])
        self.assertEqual(code, 1)
        result = json.loads(output.getvalue())
        self.assertTrue(result['valid'])
        self.assertEqual(result['publication']['state'], 'retryable_failure')
        self.assertIn('Verification result retained', errors.getvalue())
        self.assertEqual(len(self.posts), 1)

    def test_wait_can_opt_in_after_submission_and_reuse_consent(self):
        from openrsi_space.cli.commands import main
        self.client.wait = lambda _: {'metrics': {'evidenceMode': 'remote'}, 'valid': True}
        self.client.folder = lambda _: self.root / 'retained-result'
        flags = ['--publish-to-yukon', '--benchmark', self.board,
                 '--publication-title', 'My harness', '--note-file', str(self.root / 'note.md'),
                 '--no-dependencies']
        with patch('openrsi_space.client.evaluations.RemoteClient', return_value=self.client):
            for extra in [flags, ['--publish-to-yukon']]:
                output = io.StringIO()
                with redirect_stdout(output), redirect_stderr(io.StringIO()):
                    code = main(['remote', 'wait', self.eid, *extra])
                self.assertEqual(code, 0)
                self.assertEqual(json.loads(output.getvalue())['publication']['state'], 'published')
        self.assertEqual(len(self.posts), 1)

    def test_wait_without_publication_explains_next_step(self):
        from openrsi_space.cli.commands import main
        self.client.wait = lambda _: {'metrics': {'evidenceMode': 'remote'}, 'valid': True}
        self.client.folder = lambda _: self.root / 'retained-result'
        self.client.export_reference = lambda _: self.root / 'verification.json'
        output, errors = io.StringIO(), io.StringIO()
        with patch('openrsi_space.client.evaluations.RemoteClient', return_value=self.client), \
                redirect_stdout(output), redirect_stderr(errors):
            code = main(['remote', 'wait', self.eid])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())['publication']['state'], 'not_requested')
        self.assertIn('not published', errors.getvalue())
        self.assertEqual(self.posts, [])

    def test_wait_invalid_result_fails_without_publication(self):
        from openrsi_space.cli.commands import main
        self.authorize()
        self.client.wait = lambda _: {'valid': False, 'reason': 'No verified candidate'}
        output, errors = io.StringIO(), io.StringIO()
        with patch('openrsi_space.client.evaluations.RemoteClient', return_value=self.client), \
                redirect_stdout(output), redirect_stderr(errors):
            code = main(['remote', 'wait', self.eid])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output.getvalue())['publication']['state'], 'not_eligible')
        self.assertIn('nothing was published', errors.getvalue())
        self.assertEqual(self.posts, [])

    def test_wait_metadata_requires_consent_and_title(self):
        for flags in [ ['--note-file', str(self.root / 'note.md')],
                       ['--publish-to-yukon', '--benchmark', self.board,
                        '--note-file', str(self.root / 'note.md'), '--no-dependencies'] ]:
            args = self.cli.parse_args(['remote', 'wait', self.eid, *flags])
            with self.assertRaises(OpenRSIError): publication.options(args)
