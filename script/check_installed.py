"""Exercise the installed wheel; run through check.py, not from the source tree."""
import contextlib
import hashlib
import importlib
from importlib.metadata import distribution, version
import io
import json
import os
import subprocess
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

import openrsi_space
from openrsi_space.challenge import assets, catalog, papers
from openrsi_space.challenge.paths import PROBLEM_SET
from openrsi_space.cli import main
from openrsi_space.contracts.accounting import pricing_schedule
from openrsi_space.contracts.harness import validate_execution
from openrsi_space.client import evaluations
from openrsi_space.common import canonical
from openrsi_space.runtime.problem_server import load_files

scripts = {entry.name for entry in distribution("openrsi-space").entry_points
           if entry.group == "console_scripts"}
assert scripts == {"openrsi-space"}, scripts

package = Path(openrsi_space.__file__).parent
assert "site-packages" in str(package), package
command = Path(sys.executable).parent / ("openrsi-space.exe" if os.name == "nt" else "openrsi-space")
clean_env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
help_text = subprocess.check_output([str(command), "--help"], env=clean_env, text=True)
assert "usage: openrsi-space " in help_text
assert "harness" in help_text and "remote" in help_text
version_text = subprocess.check_output([str(command), "--version"], env=clean_env, text=True)
assert version_text.strip() == f"openrsi-space {version('openrsi-space')}"
expected = json.loads(Path(sys.argv[1]).read_text())
for relative, digest in expected.items():
    assert hashlib.sha256((package / relative).read_bytes()).hexdigest() == digest, relative
for old, new in {
    "problems": "challenge.catalog", "paper_library": "challenge.papers",
    "task_setup": "challenge.preparation", "tiers": "contracts.accounting",
    "executable": "harnesses.executable", "local": "integrations.dungeness.local",
    "receipts": "integrations.yukon.receipts",
}.items():
    assert importlib.import_module("openrsi_space." + old) is importlib.import_module("openrsi_space." + new)
assert importlib.import_module("openrsi_space.remote").RemoteClient is evaluations.RemoteClient
assert pricing_schedule()
for release in catalog.PROBLEM_RELEASES:
    problem = catalog.get_problem("ecdsa.fail", release=release)
    papers.load_catalog(problem["dungeness"]["knowledge_base"])
assert {p.name for p in PROBLEM_SET.iterdir()} == {"README.md", "ecdsa-fail"}
assert not list(PROBLEM_SET.rglob("*v0*"))
assert (PROBLEM_SET / "ecdsa-fail/description.md").is_file()
with tempfile.TemporaryDirectory() as temporary:
    # Exercise the installed package with an absent cache and forbidden downloads.
    # This catches wheels that contain the catalog but omit any of its PDFs.
    root = Path(temporary)
    binding = catalog.get_problem("ecdsa.fail", release="v1")["dungeness"]["knowledge_base"]
    with patch.dict(os.environ, {"OPENRSI_PAPER_CACHE": str(root / "absent-cache")}), \
            patch.object(papers, "build_opener", side_effect=AssertionError("Unexpected paper download")) as opener:
        metadata, attachments = papers.prepare_library(
            binding, root / "papers", slug="ecdsa-fail", release="v1")
        opener.assert_not_called()
    assert metadata["count"] == 8 and len(attachments) == 10
    assert not (root / "absent-cache").exists()
    files = load_files(canonical({"attachments": attachments}), root / "papers")
    assert "/ecdsa-fail/v1/knowledge-base" in files
    assert "/ecdsa-fail/v1/resources/ecdsa-core-02" in files
    runtime = Path(temporary) / "runtime"
    runtime.mkdir()
    installed = assets.install_assets(runtime, catalog.get_problem("ecdsa.fail")["dungeness"])
    assert "verifiers/ecdsa-fail/benchmark-sh" in installed
    assert (runtime / "scaffolds/ecdsa-point-add-sdk-v1/scaffold.yaml").is_file()
    harness = Path(temporary) / "harness"
    with contextlib.redirect_stdout(io.StringIO()) as output:
        assert main(["problem", "list"]) == 0
        assert "ecdsa.fail" in output.getvalue()
        assert main(["harness", "create", "wheel-check", "--executable", "--output", str(harness)]) == 0
    validate_execution(json.loads((harness / "harness.json").read_text())["execution"])
    snapshot, archive = evaluations.source_snapshot(harness)
    assert snapshot["kind"] == "harness" and archive
print("Installed wheel: file hashes, compatibility, releases, offline paper library, assets, pricing, CLI and packaging passed.")
