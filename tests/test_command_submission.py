"""Harness authoring stays executable-only while historical bundles remain readable."""
from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import re
import tempfile
import unittest

from catalyst.cli import main
from catalyst.common import make_bundle, open_bundle, validate_document


class CommandSubmissionTests(unittest.TestCase):
    def test_documented_manifest_is_complete_and_execution_only_build_is_actionable(self):
        guide = Path(__file__).resolve().parents[1] / "docs/executable-harness.md"
        examples = [json.loads(raw) for raw in re.findall(r"```json\n(.*?)\n```", guide.read_text(), re.S)]
        manifest, = [item for item in examples if item.get("kind") == "harness"]
        validate_document(manifest)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "harness.json").write_text(json.dumps(manifest["execution"]))
            error = io.StringIO()
            with redirect_stderr(error):
                self.assertNotEqual(main(["harness", "build", str(root)]), 0)
            for field in ("execution", "schema_version", "kind", "id", "title"):
                self.assertIn(field, error.getvalue())
            self.assertIn("openrsi-space harness create", error.getvalue())

    def test_starter_and_derived_harness_keep_the_executable_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, derived = root / "source", root / "derived"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["harness", "create", "source", "--output", str(source)]), 0)
                self.assertEqual(main(["harness", "create", "derived", "--from", str(source),
                                       "--output", str(derived)]), 0)
            first = json.loads((source / "harness.json").read_text())
            second = json.loads((derived / "harness.json").read_text())
            self.assertEqual(first["execution"]["interface"], "catalyst-exec-v1")
            self.assertEqual(first["execution"], second["execution"])
            self.assertEqual((source / "agent.py").read_bytes(), (derived / "agent.py").read_bytes())
            self.assertNotIn("agent", first)
            self.assertEqual(second["derived_from"]["id"], "source")

    def test_native_creation_fails_before_writing_source(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "legacy"
            error = io.StringIO()
            with redirect_stderr(error):
                self.assertNotEqual(main(["harness", "create", "legacy",
                                          "--agent", "agent:projects/dungeness/codex-openai",
                                          "--output", str(target)]), 0)
            self.assertIn("Bundled agents are retired", error.getvalue())
            self.assertFalse(target.exists())

    def test_legacy_bundle_can_be_read_but_not_used_to_create_a_new_harness(self):
        document = {"schema_version": 1, "kind": "harness", "id": "legacy", "title": "Old run",
                    "agent": "agent:projects/dungeness/claude"}
        snapshot, archive = make_bundle({"harness.json": json.dumps(document).encode()})
        self.assertEqual(open_bundle(archive)[0], snapshot)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "harness.json").write_text(json.dumps(document))
            target = root / "derived"
            error = io.StringIO()
            with redirect_stderr(error):
                self.assertNotEqual(main(["harness", "create", "derived", "--from", str(root),
                                          "--output", str(target)]), 0)
            self.assertIn("Migrate it to catalyst-exec-v1", error.getvalue())
            self.assertFalse(target.exists())
