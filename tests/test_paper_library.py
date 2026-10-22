import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from catalyst.common import CatalystError, canonical
from catalyst.challenge.papers import cached_paper, load_catalog, prepare_library, validate_download_url
from catalyst.challenge.catalog import get_problem
from catalyst.runtime.problem_server import load_files
from library_fixture import install_fixture


class PaperLibraryTests(unittest.TestCase):
    def test_catalog_rejects_changed_or_retired_bindings(self):
        binding = get_problem("ecdsa.fail")["dungeness"]["knowledge_base"]
        for invalid in ({**binding, "sha256": "0" * 64},
                        {**binding, "id": "ecdsa-papers-v2"},
                        {**binding, "sha256": "380233e137617f6cd2bbeedcd591023b05da7322ecdd8d943dabab0302df04cf"}):
            with self.assertRaises(CatalystError):
                load_catalog(invalid)

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
            with patch("catalyst.challenge.papers.build_opener") as opener:
                self.assertEqual(cached_paper(entry, cache).read_bytes(), data)
                opener.assert_not_called()
                (cache / "test.pdf").write_bytes(b"tampered")
                response = opener.return_value.open.return_value.__enter__.return_value
                response.read.side_effect = [b"bad", b""]
                with self.assertRaisesRegex(CatalystError, "SHA-256"):
                    cached_paper(entry, cache)
                self.assertEqual({p.name for p in cache.iterdir()}, {"test.pdf"})
