import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from openrsi_space.common import OpenRSIError, canonical
from openrsi_space.challenge.papers import cached_paper, load_catalog, prepare_library, validate_download_url
from openrsi_space.challenge.catalog import get_problem
from openrsi_space.runtime.problem_server import load_files
from library_fixture import install_fixture


class PaperLibraryTests(unittest.TestCase):
    def test_catalog_rejects_changed_or_retired_bindings(self):
        binding = get_problem("ecdsa.fail")["dungeness"]["knowledge_base"]
        for invalid in ({**binding, "sha256": "0" * 64},
                        {**binding, "id": "ecdsa-papers-v2"},
                        {**binding, "sha256": "8aee712ce329af7efbb4b7ec3f8e4c0007c98bedecda3f140633f9dfd70c697e"},
                        {**binding, "sha256": "380233e137617f6cd2bbeedcd591023b05da7322ecdd8d943dabab0302df04cf"}):
            with self.assertRaises(OpenRSIError):
                load_catalog(invalid)

    def test_eight_paper_release_prepares_offline_with_only_selected_files(self):
        from openrsi_space.challenge.papers import BUNDLED_PAPERS
        binding = get_problem("ecdsa.fail")["dungeness"]["knowledge_base"]
        catalog = load_catalog(binding)
        expected = {
            "2606.02235v1", "1905.07682v1", "2407.20167v1", "2507.23079v1",
            "2110.08973v3", "2609.28882v1", "2510.10967v1", "2020/077",
        }
        self.assertEqual({p["pdf_url"].split("/pdf/")[-1] if "arxiv.org" in p["pdf_url"]
                          else p["pdf_url"].removeprefix("https://eprint.iacr.org/").removesuffix(".pdf")
                          for p in catalog["papers"]}, expected)
        self.assertEqual({p.name for p in BUNDLED_PAPERS.glob("*.pdf")},
                         {p["file"] for p in catalog["papers"]})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict("os.environ", {"OPENRSI_PAPER_CACHE": str(root / "empty-cache")}), \
                    patch("openrsi_space.challenge.papers.build_opener") as opener:
                metadata, entries = prepare_library(binding, root / "files", slug="ecdsa-fail", release="v1")
                opener.assert_not_called()
            self.assertEqual(metadata["count"], 8)
            self.assertEqual(metadata["url"], "http://gateway:8080/ecdsa-fail/v1/knowledge-base")
            files = load_files(canonical({"attachments": entries}), root / "files")
            for paper in catalog["papers"]:
                self.assertIn(paper["license_url"], {
                    "https://creativecommons.org/licenses/by/4.0/",
                    "https://creativecommons.org/publicdomain/zero/1.0/",
                })
                path, _ = files["/task/files/" + paper["file"]]
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), paper["sha256"])

    def test_download_hosts_are_bounded_and_never_accept_credentials_or_queries(self):
        for url in ("https://arxiv.org/pdf/1706.06752", "https://eprint.iacr.org/2026/1128.pdf"):
            validate_download_url(url)
        for url in ("http://arxiv.org/pdf/1", "https://attacker.invalid/paper.pdf",
                    "https://key@arxiv.org/pdf/1", "https://arxiv.org:8443/pdf/1",
                    "https://eprint.iacr.org/2026/1128.pdf?url=other"):
            with self.assertRaises(OpenRSIError):
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
            with patch("openrsi_space.challenge.papers.build_opener") as opener:
                self.assertEqual(cached_paper(entry, cache).read_bytes(), data)
                opener.assert_not_called()
                (cache / "test.pdf").write_bytes(b"tampered")
                response = opener.return_value.open.return_value.__enter__.return_value
                response.read.side_effect = [b"bad", b""]
                with self.assertRaisesRegex(OpenRSIError, "SHA-256"):
                    cached_paper(entry, cache)
                self.assertEqual({p.name for p in cache.iterdir()}, {"test.pdf"})
