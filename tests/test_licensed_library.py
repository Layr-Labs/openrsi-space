import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from catalyst.common import CatalystError
from catalyst.challenge.catalog import get_problem
from catalyst.challenge.papers import BUNDLED_PAPERS, cached_paper, load_catalog, matches


class LicensedLibraryTests(unittest.TestCase):
    def catalog(self):
        return load_catalog(get_problem("ecdsa.fail", release="v1")["dungeness"]["knowledge_base"])

    def test_licensed_selection_preserves_required_work_and_grading(self):
        catalog = self.catalog()
        self.assertEqual(catalog["count"], 8)
        self.assertEqual(len({p["sha256"] for p in catalog["papers"]}), 8)
        self.assertEqual(len({p["id"] for p in catalog["papers"]}), 8)
        allowed = {"https://creativecommons.org/licenses/by/4.0/",
                   "https://creativecommons.org/licenses/by-sa/4.0/",
                   "https://creativecommons.org/publicdomain/zero/1.0/"}
        for paper in catalog["papers"]:
            self.assertIn(paper["license_url"], allowed)
            self.assertTrue(paper["authors"])
            self.assertEqual(paper["modifications"], "none")
            if "arxiv.org" in paper["pdf_url"]:
                self.assertRegex(paper["pdf_url"], r"v\d+$")
        required = [p for p in catalog["papers"] if p.get("arxiv_id") == "2606.02235v1"]
        self.assertEqual(len(required), 1)
        self.assertEqual(required[0]["license_url"], "https://creativecommons.org/licenses/by/4.0/")
        self.assertTrue(matches(BUNDLED_PAPERS / required[0]["file"], required[0]))
        grading = copy.deepcopy(get_problem("ecdsa.fail", release="v1"))
        grading.pop("release")
        grading["dungeness"].pop("knowledge_base")
        from catalyst.common import canonical
        self.assertEqual(hashlib.sha256(canonical(grading)).hexdigest(),
                         "762f1e2cb6054e88de4d4bb04bdbc496b186c9690721f8b8d767faf43b7cf250")
        evidence = json.loads((BUNDLED_PAPERS.parent / "licenses-v1.json").read_text())
        self.assertEqual({p["id"] for p in evidence["papers"]}, {p["id"] for p in catalog["papers"]})
        self.assertEqual({p["path"] for p in evidence["excluded_from_supplied_collection"]},
                         {"2410.00899v1.pdf", "2607.13816v2.pdf"})
        self.assertFalse({p["sha256"] for p in evidence["excluded_from_supplied_collection"]}
                         & {p["sha256"] for p in catalog["papers"]})

    def test_complete_library_is_bundled_without_network_or_cache(self):
        catalog = self.catalog()
        selected = catalog["papers"]
        self.assertEqual(len(selected), 8)
        self.assertEqual({p.name for p in BUNDLED_PAPERS.glob("*.pdf")}, {p["file"] for p in selected})
        with tempfile.TemporaryDirectory() as folder, patch("catalyst.challenge.papers.build_opener") as opener:
            for paper in selected:
                path = cached_paper(paper, Path(folder) / "absent-cache")
                self.assertTrue(matches(path, paper))
                self.assertEqual(path.parent, BUNDLED_PAPERS)
            opener.assert_not_called()

    def test_corrupt_or_symlinked_bundle_fails_closed(self):
        data = b"%PDF-1.4\nfixture"
        entry = {"id": "fixture", "file": "paper.pdf", "bytes": len(data),
                 "sha256": hashlib.sha256(data).hexdigest(), "pdf_url": "https://arxiv.org/pdf/1"}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            bundle = root / "bundle"
            bundle.mkdir()
            with patch("catalyst.challenge.papers.BUNDLED_PAPERS", bundle), \
                    patch("catalyst.challenge.papers.build_opener") as opener:
                paper = bundle / entry["file"]
                paper.write_bytes(b"tampered")
                with self.assertRaisesRegex(CatalystError, "Bundled task paper"):
                    cached_paper(entry, root / "cache")
                paper.unlink()
                target = root / "outside.pdf"
                target.write_bytes(data)
                paper.symlink_to(target)
                with self.assertRaisesRegex(CatalystError, "Bundled task paper"):
                    cached_paper(entry, root / "cache")
                opener.assert_not_called()


class CurrentProblemTests(unittest.TestCase):
    def test_current_release_checks_exact_installed_digest(self):
        from catalyst.client.catalog import PublicCatalog
        from catalyst.challenge.catalog import initial_problems
        from catalyst.contracts.results import digest
        client = PublicCatalog('https://verifier.example.test')
        version = digest(initial_problems(release='v1'))
        advertised = {'problem_version': version, 'problem_versions': [
            {'id': 'ecdsa.fail', 'slug': 'ecdsa-fail', 'release': 'v1', 'version': version}]}
        with patch.object(client, 'search', return_value=advertised):
            self.assertTrue(client.current_problem()['installed'])
        advertised['problem_versions'][0]['release'] = 'v99'
        with patch.object(client, 'search', return_value=advertised):
            self.assertFalse(client.current_problem()['installed'])
        advertised['problem_versions'] = []
        with patch.object(client, 'search', return_value=advertised):
            with self.assertRaises(CatalystError):
                client.current_problem()
