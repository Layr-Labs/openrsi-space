import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from catalyst.common import CatalystError, canonical
from catalyst.paper_library import cached_paper, load_catalog, prepare_library, validate_download_url
from catalyst.problems import get_problem
from catalyst.runtime.problem_server import load_files
from library_fixture import install_fixture


class PaperLibraryTests(unittest.TestCase):
    def test_catalog_preserves_the_32_paper_collection_and_adds_18_distinct_papers(self):
        catalog = load_catalog(get_problem("ecdsa.fail")["dungeness"]["knowledge_base"])
        self.assertEqual(len({p["sha256"] for p in catalog["papers"]}), 50)
        self.assertEqual(len({p["id"] for p in catalog["papers"]}), 50)
        core = [p for p in catalog["papers"] if p["origin"]["collection"] == "ecdsa-32-raw-paper-kb-v1"]
        extra = [p for p in catalog["papers"] if p["origin"]["collection"] == "curated-extension"]
        self.assertEqual((len(core), len(extra)), (32, 18))
        for paper in core:
            self.assertEqual(paper["file"], paper["origin"]["file"])
            self.assertEqual(paper["sha256"], paper["origin"]["sha256"])
        for paper in extra:
            self.assertRegex(paper["arxiv_id"], r"^\d{4}\.\d{4,5}v\d+$")
            self.assertIn("creativecommons.org/", paper["license_url"])
        for paper in catalog["papers"]:
            self.assertRegex(paper["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(paper["modifications"], "none")
            self.assertTrue(paper["source_url"].startswith("https://"))
            if paper["license_url"] is None:
                self.assertEqual(paper["license_status"], "not-recorded-in-source-collection")
        with self.assertRaises(CatalystError):
            load_catalog({"id": catalog["id"], "sha256": "0" * 64})

    def test_download_hosts_are_bounded_and_never_accept_credentials_or_queries(self):
        for url in ("https://arxiv.org/pdf/1706.06752", "https://eprint.iacr.org/2026/1128.pdf"):
            validate_download_url(url)
        for url in ("http://arxiv.org/pdf/1", "https://attacker.invalid/paper.pdf",
                    "https://key@arxiv.org/pdf/1", "https://arxiv.org:8443/pdf/1",
                    "https://eprint.iacr.org/2026/1128.pdf?url=other"):
            with self.assertRaises(CatalystError):
                validate_download_url(url)
    def test_assembly_copies_verified_papers_and_serves_original_attribution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install_fixture(self, root)
            metadata, entries = prepare_library({}, root / "files")
            self.assertEqual(metadata["count"], 50)
            self.assertEqual(len(entries), 51)
            files = load_files(canonical({"attachments": entries}), root / "files")
            self.assertEqual(len(files), 51)
            catalog = json.loads((root / "files/knowledge-base.json").read_text())
            self.assertEqual(len(catalog["papers"]), 50)
            self.assertTrue(all(p["url"].startswith("http://gateway:8080/task/files/")
                                for p in catalog["papers"]))

    def test_cache_validates_bytes_and_never_accepts_a_mismatch(self):
        data = b"%PDF-1.4\nfixture"
        entry = {"id": "test", "file": "test.pdf", "bytes": len(data),
                 "sha256": hashlib.sha256(data).hexdigest(), "pdf_url": "https://arxiv.org/pdf/1"}
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            (cache / "test.pdf").write_bytes(data)
            with patch("catalyst.paper_library.build_opener") as opener:
                self.assertEqual(cached_paper(entry, cache).read_bytes(), data)
                opener.assert_not_called()
                (cache / "test.pdf").write_bytes(b"tampered")
                response = opener.return_value.open.return_value.__enter__.return_value
                response.read.side_effect = [b"bad", b""]
                with self.assertRaisesRegex(CatalystError, "SHA-256"):
                    cached_paper(entry, cache)
                self.assertEqual({p.name for p in cache.iterdir()}, {"test.pdf"})
