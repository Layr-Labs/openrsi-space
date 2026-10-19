"""Small offline library used by task-assembly contract tests."""
import hashlib
from pathlib import Path
from unittest.mock import patch


def install_fixture(test, root):
    raw = b"%PDF-1.4\nSynthetic contract-test paper; not a research document.\n%%EOF\n"
    source = Path(root) / "fixture.pdf"
    source.write_bytes(raw)
    catalog = {"schema_version": 1, "id": "fixture-library", "count": 50, "papers": [
        {"id": f"paper-{i}", "file": f"paper-{i}.pdf", "sha256": hashlib.sha256(raw).hexdigest(),
         "bytes": len(raw), "title": f"Fixture {i}", "media_type": "application/pdf"}
        for i in range(50)]}
    for mock in (
        patch("catalyst.paper_library.load_catalog", return_value=catalog),
        patch("catalyst.paper_library.cached_paper", return_value=source),
    ):
        mock.start()
        test.addCleanup(mock.stop)
