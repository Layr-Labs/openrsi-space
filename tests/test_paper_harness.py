"""Offline contracts for the submitted paper harness; no credentials or model calls."""
import base64
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from catalyst.cheat_filter import screen
from catalyst.common import open_bundle
from catalyst.remote import MAX_SOURCE_BYTES, request_body


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "harnesses/ecdsa-paper-2606-02235"


class PaperHarnessTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("paper_harness", HARNESS / "agent.py")
        self.agent = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.agent)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.task = {
            "model_provider": "openai-chatgpt",
            "model": "gpt-6-astra",
            "reasoning_effort": "high",
            "gateway": "http://dungeness.invalid/codex",
            "budget": {"max_usd": 3},
            "workspace": str(self.workspace),
            "instruction": "Use the trusted evaluate command; candidate paths: src/point_add.",
        }

    def test_remote_package_contains_offline_paper_and_passes_screening(self):
        with patch.dict(os.environ, {"CATALYST_LOCAL_TEST": "", "CATALYST_LOCAL_ECDSA": ""}):
            body = request_body(HARNESS, "https://example.invalid")
        archive = base64.b64decode(body["source"]["archive_base64"])
        self.assertLess(len(archive), MAX_SOURCE_BYTES)
        snapshot, files = open_bundle(archive)
        self.assertEqual(snapshot["id"], "ecdsa-paper-2606-02235")
        self.assertNotIn("evaluation.json", files)
        self.assertNotIn("verification.json", files)
        self.assertTrue(files["references/paper.pdf"].startswith(b"%PDF"))
        self.assertNotIn("references/paper.txt", files)
        self.assertNotIn("references/research-brief.md", files)
        self.assertIn(b"2606.02235v1", files["references/provenance.json"])
        self.assertEqual(screen(files, "harness")["status"], "passed")
        self.agent.check_references()
        self.assertEqual(body["evaluation"]["max_model_credits"], 3)
        self.assertEqual(body["evaluation"]["model"], {
            "provider": "openai-chatgpt", "name": "gpt-6-astra", "reasoning_effort": "high",
        })

    def test_missing_or_modified_paper_fails_before_codex_starts(self):
        copy = self.root / "harness"
        shutil.copytree(HARNESS, copy, ignore=shutil.ignore_patterns("__pycache__"))
        with patch.object(self.agent, "ROOT", copy):
            paper = copy / "references/paper.pdf"
            paper.write_text("A different paper.")
            with self.assertRaisesRegex(SystemExit, "checksum mismatch"):
                self.agent.make_instruction(self.task)
            paper.unlink()
            with self.assertRaises(FileNotFoundError):
                self.agent.make_instruction(self.task)

    def test_prompt_uses_runtime_budget_and_offline_references(self):
        instruction = self.agent.make_instruction(self.task)
        self.assertIn(self.task["instruction"], instruction)
        self.assertIn("$3 normalized", instruction)
        self.assertIn("$2.55", instruction)
        self.assertIn(str(HARNESS / "references"), instruction)
        self.assertIn("arXiv:2606.02235v1", instruction)
        self.assertIn("restore the best", instruction)

    def invoke_with_fake_codex(self, *, fail=False):
        task_file = self.root / "task.json"
        task_file.write_text(json.dumps(self.task))
        auth_file = self.root / "temporary-auth.json"
        # A deliberately fake credential; never read the developer's Codex home.
        auth_file.write_text('{"tokens":{"access_token":"offline-fixture"}}')
        homes = []

        def fake_codex(argv, *, input, text, cwd, env):
            home = Path(env["CODEX_HOME"])
            homes.append(home)
            config = tomllib.loads((home / "config.toml").read_text())
            self.assertEqual(config["model_provider"], "dungeness")
            self.assertEqual(config["model_providers"]["dungeness"]["base_url"], self.task["gateway"])
            self.assertEqual(config["web_search"], "disabled")
            self.assertNotIn("OPENAI_API_KEY", env)
            self.assertEqual((home / "auth.json").read_bytes(), auth_file.read_bytes())
            self.assertEqual((home / "auth.json").stat().st_mode & 0o777, 0o600)
            self.assertEqual(argv[argv.index("--model") + 1], self.task["model"])
            self.assertIn('model_reasoning_effort="high"', argv)
            self.assertEqual(argv[-1], "-")
            self.assertIn("2606.02235v1", input)
            self.assertTrue(text)
            self.assertEqual(cwd, str(self.workspace))
            if fail:
                raise OSError("Fake Codex startup failure")
            # Mirrors a budget-stopped model process: independent verification
            # still decides whether the already-written candidate is valid.
            return subprocess.CompletedProcess(argv, 17)

        with (
            patch.dict(os.environ, {"CATALYST_TASK": str(task_file), "OPENAI_API_KEY": "must-not-inherit"}),
            patch.object(self.agent, "AUTH_FILE", auth_file),
            patch.object(self.agent, "RAM_ROOT", self.root),
            patch.object(self.agent.subprocess, "run", side_effect=fake_codex) as command,
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            if fail:
                with self.assertRaisesRegex(OSError, "Fake Codex startup"):
                    self.agent.run()
            else:
                self.agent.run()
                self.assertEqual(json.loads(output.getvalue()), {"event": "codex_finished", "exit_code": 17})
            command.assert_called_once()
        self.assertEqual(len(homes), 1)
        self.assertFalse(homes[0].exists())
        self.assertTrue(auth_file.exists())  # Original temporary mount is worker-owned.

    def test_native_route_and_auth_cleanup_after_budget_stop(self):
        self.invoke_with_fake_codex()

    def test_auth_cleanup_after_codex_startup_failure(self):
        self.invoke_with_fake_codex(fail=True)

    def test_other_provider_is_rejected_before_reading_credentials(self):
        self.task["model_provider"] = "openai"
        task_file = self.root / "task.json"
        task_file.write_text(json.dumps(self.task))
        with (
            patch.dict(os.environ, {"CATALYST_TASK": str(task_file)}),
            patch.object(self.agent.shutil, "copyfile") as copy_auth,
            patch.object(self.agent.subprocess, "run") as command,
        ):
            with self.assertRaisesRegex(SystemExit, "requires the ChatGPT"):
                self.agent.run()
            copy_auth.assert_not_called()
            command.assert_not_called()

    def test_command_gateway_mode_never_reads_native_credentials(self):
        self.task["gateway_auth"] = "placeholder"
        task_file = self.root / "task.json"
        task_file.write_text(json.dumps(self.task))

        def fake_codex(argv, **kwargs):
            home = Path(kwargs["env"]["CODEX_HOME"])
            config = tomllib.loads((home / "config.toml").read_text())
            provider = config["model_providers"]["dungeness"]
            self.assertFalse(provider["requires_openai_auth"])
            self.assertEqual(provider["env_key"], "OPENAI_API_KEY")
            self.assertEqual(kwargs["env"]["OPENAI_API_KEY"], "testbed")
            self.assertFalse((home / "auth.json").exists())
            return subprocess.CompletedProcess(argv, 0)

        with (
            patch.dict(os.environ, {"CATALYST_TASK": str(task_file)}),
            patch.object(self.agent, "RAM_ROOT", self.root),
            patch.object(self.agent.shutil, "copyfile") as copy_auth,
            patch.object(self.agent.subprocess, "run", side_effect=fake_codex),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.agent.run()
            copy_auth.assert_not_called()


if __name__ == "__main__":
    unittest.main()
