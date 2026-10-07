"""Optional offline contract check against the user's real pinned Dungeness.

It runs the real manifest validators and compiler. Repository checkout is replaced
with a tiny fixture; Docker, external network, credentials and model calls are unused.
"""
from contextlib import redirect_stdout
from datetime import datetime, timezone
import importlib.util
import io
import os
from pathlib import Path
import runpy
import shutil
import tempfile
import unittest
from unittest.mock import patch

import yaml

from catalyst.cli import main
from catalyst.dungeness import configure, prepare
from catalyst.common import snapshot_directory


@unittest.skipUnless(os.environ.get("CATALYST_DUNGENESS"), "Set CATALYST_DUNGENESS for the real compiler contract check.")
class DungenessContractTest(unittest.TestCase):
    def test_generated_problem_and_knowledge_compile_in_real_dungeness(self):
        self.compile_harness(executable=False)

    def test_submitted_executable_compiles_with_generic_adapter_in_real_dungeness(self):
        self.compile_harness(executable=True)

    def compile_harness(self, executable):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state, problem, harness = root / "state", root / "problem", root / "harness"
            configure(state, Path(os.environ["CATALYST_DUNGENESS"]))
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--state", str(state), "problem", "create", "toy", "--output", str(problem),
                                       "--repository", "https://example.org/source.git", "--commit", "a"*40]), 0)
                self.assertEqual(main(["--state", str(state), "harness", "create", "notes",
                                       "--output", str(harness), *(["--executable"] if executable else [])]), 0)
            if executable:
                snapshot, _ = snapshot_directory(harness)
                build_record = {"id": "a" * 64, "source_digest": snapshot["version"],
                                "image_id": "sha256:" + "b" * 64,
                                "artifact_tag": "catalyst-image:" + "b" * 64}
                with patch("catalyst.executable.inspect_build", return_value=build_record):
                    meta = prepare(state, problem, harness, 1, 10000,
                                   build_id=build_record["id"], model="gpt-5.6-sol")
            else:
                meta = prepare(state, problem, harness, 1, 10000)
            runtime = Path(meta["runtime"])
            spec = yaml.safe_load(Path(meta["spec_path"]).read_text())
            cli = runpy.run_path(str(runtime / "dungeness"), run_name="contract_check")
            cli["validate_run_spec_knowledge_base"](spec)
            cli["validate_run_spec_web_search"](spec)
            module_spec = importlib.util.spec_from_file_location("dungeness_contract_compiler", runtime / "src/dungeness/compiler.py")
            compiler = importlib.util.module_from_spec(module_spec)
            module_spec.loader.exec_module(compiler)

            def fixture_checkout(url, commit, destination):
                shutil.copytree(problem / "source", destination)

            def split_reference(reference):
                namespace, _, identity = reference.split(":", 1)[1].rpartition("/")
                return namespace, identity

            task_ns, task_id = split_reference(spec["task"])
            agent_ns, agent_id = split_reference(spec["agent"])
            rendered = None
            try:
                with patch.object(compiler, "checkout", fixture_checkout), patch.object(
                    compiler, "commit_timestamp", return_value=datetime(2026, 1, 1, tzinfo=timezone.utc)
                ), redirect_stdout(io.StringIO()):
                    rendered = compiler.build_task(
                        task_id=task_id, task_namespace=task_ns, agent_id=agent_id, agent_namespace=agent_ns,
                        run_id=meta["id"], namespace="projects/catalyst", checkpoint=spec["checkpoint"],
                        max_usd=1, max_model_tokens=10000, run_spec=meta["spec_path"],
                    )
                self.assertTrue((rendered / "harbor-job.yaml").is_file())
                compose = yaml.safe_load((rendered / "environment/docker-compose.yaml").read_text())
                self.assertTrue(compose["networks"]["agent_internal"]["internal"])
                self.assertEqual(compose["services"]["main"]["networks"], ["agent_internal"])
                self.assertIn("knowledge", (rendered / "instruction.md").read_text().lower())
                self.assertTrue((rendered / "tests/grade.py").is_file())
                if executable:
                    job = yaml.safe_load((rendered / "harbor-job.yaml").read_text())
                    adapter = job["agents"][0]
                    self.assertEqual(adapter["import_path"], "catalyst_executable:CatalystExecutable")
                    self.assertNotIn("name", adapter)
                    self.assertEqual(adapter["kwargs"]["task_input"]["candidate_paths"], ["solution.py"])
                    self.assertEqual(adapter["env"], {"OPENAI_API_KEY": "testbed"})
                    self.assertIn(build_record["artifact_tag"],
                                  (rendered / "environment/Dockerfile").read_text())
            finally:
                if rendered:
                    shutil.rmtree(rendered.parent)


if __name__ == "__main__":
    unittest.main()
