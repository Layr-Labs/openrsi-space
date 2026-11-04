"""Versioned resource discovery supports mixed media without model/network calls."""
import hashlib
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

from openrsi_space.common import OpenRSIError, canonical
from openrsi_space.challenge.resources import write_resource_catalog
from openrsi_space.challenge.papers import prepare_library
from openrsi_space.runtime.problem_server import handler_for, load_files
from library_fixture import install_fixture


class KnowledgeBaseTests(unittest.TestCase):
    def test_mixed_resources_have_stable_ids_and_verified_downloads(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            resources = []
            for identity, filename, kind, media, raw in (
                ('notes', 'notes.md', 'notes', 'text/markdown', b'# Notes\n'),
                ('dataset', 'data.csv', 'dataset', 'text/csv', b'x,y\n1,2\n'),
                ('code', 'example.py', 'code', 'text/plain', b'print(1)\n'),
                ('paper', 'article.pdf', 'paper', 'application/pdf', b'%PDF-fixture'),
            ):
                (root / filename).write_bytes(raw)
                resources.append({'id': identity, 'filename': filename, 'kind': kind, 'title': identity,
                                  'media_type': media, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
            metadata, attachments = write_resource_catalog(root, {'id': 'mixed-v1', 'rights_notice': 'Original licenses apply.'}, resources, 'ecdsa-fail', 'v1')
            self.assertEqual(metadata['count'], 4)
            catalog = json.loads((root / 'resources.json').read_text())
            self.assertEqual(catalog['rights_notice'], 'Original licenses apply.')
            self.assertEqual(catalog['resources'][0]['url'], 'http://gateway:8080/ecdsa-fail/v1/resources/notes')
            payload = canonical({'schema_version': 1, 'attachments': attachments})
            files = load_files(payload, root)
            with ThreadingHTTPServer(('127.0.0.1', 0), handler_for(payload, hashlib.sha256(payload).hexdigest(), files)) as server:
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                base = f'http://127.0.0.1:{server.server_port}'
                try:
                    for path in ('/ecdsa-fail/v1/resources/notes', '/ecdsa-fail/resources/notes', '/task/files/notes.md'):
                        with urlopen(base + path) as response:
                            self.assertEqual(response.read(), b'# Notes\n')
                            self.assertEqual(response.headers['Content-Type'], 'text/markdown')
                            self.assertIn('notes.md', response.headers['Content-Disposition'])
                    for path in ('/ecdsa-fail/v2/resources/notes', '/other/v1/resources/notes',
                                 '/ecdsa-fail/v1/resources/unknown', '/ecdsa-fail/v1/resources/notes?url=other'):
                        with self.assertRaises(HTTPError) as raised:
                            urlopen(base + path)
                        self.assertEqual(raised.exception.code, 404)
                        raised.exception.close()
                    with urlopen(base + '/ecdsa-fail/v1/knowledge-base') as response:
                        self.assertEqual(json.load(response), catalog)
                        self.assertEqual(response.headers['X-Content-SHA256'], metadata['sha256'])
                finally:
                    server.shutdown()
                    thread.join()
            (root / 'notes.md').write_bytes(b'changed')
            with self.assertRaises(OpenRSIError):
                write_resource_catalog(root, {'id': 'mixed-v1'}, resources, 'ecdsa-fail', 'v1')

    def test_paper_adapter_preserves_legacy_catalog_and_original_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            install_fixture(self, root)
            metadata, attachments = prepare_library({}, root / 'files', slug='ecdsa-fail', release='v1')
            old = json.loads((root / 'files/knowledge-base.json').read_text())
            new = json.loads((root / 'files/resources.json').read_text())
            self.assertEqual(len(old['papers']), 50)
            self.assertEqual(len(new['resources']), 50)
            self.assertEqual(len(attachments), 52)
            self.assertTrue(old['papers'][0]['url'].startswith('http://gateway:8080/task/files/'))
            self.assertEqual(new['resources'][0]['sha256'], old['papers'][0]['sha256'])
            self.assertEqual(new['resources'][0]['kind'], 'paper')
            self.assertEqual(metadata['url'], 'http://gateway:8080/ecdsa-fail/v1/knowledge-base')

    def test_resource_identity_and_media_headers_are_validated(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'notes.txt').write_bytes(b'notes')
            item = {'id': 'notes', 'filename': 'notes.txt', 'kind': 'notes', 'title': 'Notes',
                    'media_type': 'text/plain', 'bytes': 5, 'sha256': hashlib.sha256(b'notes').hexdigest()}
            for changes in ({'id': '../secret'}, {'filename': '../secret'}, {'filename': 'resources.json'},
                            {'media_type': 'text/plain\r\nX-Injected: yes'}, {'sha256': 'a' * 64}):
                with self.subTest(changes=changes), self.assertRaises(OpenRSIError):
                    write_resource_catalog(root, {'id': 'test'}, [{**item, **changes}], 'ecdsa-fail', 'v1')
            with self.assertRaises(OpenRSIError):
                write_resource_catalog(root, {'id': 'test'}, [item, item], 'ecdsa-fail', 'v1')
