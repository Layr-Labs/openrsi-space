import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from catalyst.common import CatalystError, canonical
from catalyst.challenge.papers import load_catalog
from catalyst.challenge.catalog import get_problem, initial_problems, is_official_problem_set
from catalyst.remote import request_body
from harness_fixture import create_harness


class ProblemReleaseTests(unittest.TestCase):
    def test_v0_pins_only_the_requested_arxiv_paper_and_preserves_v1(self):
        v0 = get_problem('ecdsa.fail', release='v0')
        v1 = get_problem('ecdsa.fail', release='v1')
        self.assertEqual(get_problem('ecdsa.fail'), v1)
        one = load_catalog(v0['dungeness']['knowledge_base'])
        full = load_catalog(v1['dungeness']['knowledge_base'])
        self.assertEqual((one['count'], len(one['papers'])), (1, 1))
        self.assertEqual((full['count'], len(full['papers'])), (50, 50))
        paper, = one['papers']
        self.assertEqual(paper['pdf_url'], 'https://arxiv.org/pdf/2606.02235v1')
        self.assertEqual(paper['authors'], ['André Schrottenloher'])
        self.assertEqual(paper['sha256'], '8744ef6db6c60b62d952a1dd24e5bd433242af970f4755c8b49b020a731584af')
        for problem, catalog in ((v0, one), (v1, full)):
            self.assertEqual(problem['dungeness']['knowledge_base']['sha256'],
                             hashlib.sha256(canonical(catalog)).hexdigest())
        equivalent = copy.deepcopy(v0)
        equivalent['release'] = 'v1'
        equivalent['dungeness']['knowledge_base'] = v1['dungeness']['knowledge_base']
        self.assertEqual(equivalent, v1)

    def test_only_exact_installed_release_pins_are_official(self):
        for release in ('v0', 'v1'):
            manifest = initial_problems(release=release)
            self.assertTrue(is_official_problem_set(manifest))
            manifest[0]['release'] = 'v1' if release == 'v0' else 'v0'
            self.assertFalse(is_official_problem_set(manifest))
        for release in ('v2', '../initial', ''):
            with self.assertRaises(CatalystError):
                initial_problems(release=release)
        for binding in ({'id': '../ecdsa-papers-v0'}, {'id': 'ecdsa-papers-v0', 'sha256': '0' * 64}):
            with self.assertRaises(CatalystError):
                load_catalog(binding)

    def test_remote_request_preserves_selected_release(self):
        with tempfile.TemporaryDirectory() as folder:
            harness = Path(folder) / 'harness'
            create_harness(harness)
            v0 = request_body(harness, 'https://verifier.example.test', problem_release='v0')
            v1 = request_body(harness, 'https://verifier.example.test')
            self.assertEqual(v0['problem_set'], initial_problems(release='v0'))
            self.assertEqual(v1['problem_set'], initial_problems(release='v1'))
            self.assertNotEqual(canonical(v0['problem_set']), canonical(v1['problem_set']))
