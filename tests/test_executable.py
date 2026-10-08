from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from catalyst.cli import main
from catalyst.common import CatalystError, snapshot_directory, validate_document, write_json
from catalyst.dungeness import configure, prepare
from catalyst.executable import build, inspect_build, install_agent, model_profile, RUNTIME
from catalyst.problems import develop, initial_problems, validate_workspace


def commit(root):
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.name=Test", "-c",
                    "user.email=test@localhost", "-c", "commit.gpgsign=false",
                    "commit", "-qm", "fixture"], check=True)
    return subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"]).decode().strip()


class ExecutableTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.state = self.root / "state"
        self.harness = self.root / "harness"
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["harness", "create", "solver", "--executable",
                                   "--output", str(self.harness)]), 0)
        self.snapshot, _ = snapshot_directory(self.harness)
        self.image = "sha256:" + "a" * 64
        self.docker_calls = []

    def tearDown(self):
        self.temp.cleanup()

    def docker(self, argv, **kwargs):
        self.docker_calls.append(argv)
        if argv[0] == "info":
            return "linux/aarch64"
        if argv[:2] == ["image", "inspect"]:
            if "--format" in argv:
                return self.image
            return json.dumps([{"Id": self.image, "Config": {
                "Labels": {"catalyst.source": self.snapshot["version"]}}}])
        return ""

    def test_source_is_executable_and_cannot_select_host_code(self):
        doc = self.snapshot["document"]
        self.assertNotIn("agent", doc)
        self.assertIn("agent.py", self.snapshot["files"])
        for changes in ({"agent": "agent:malicious/code"},
                        {"execution": {**doc["execution"], "import_path": "evil:HostCode"}},
                        {"execution": {**doc["execution"], "entrypoint": "sh -c anything"}},
                        {"execution": {**doc["execution"], "dockerfile": "../Dockerfile"}}):
            with self.assertRaises(CatalystError):
                validate_document({**doc, **changes})

    def test_build_reuses_source_but_checks_image_provenance(self):
        (self.harness / ".env").write_text("NEVER_BUILD=this-secret")
        with patch("catalyst.executable.docker_output", self.docker):
            first = build(self.state, self.harness)
            builds = sum(call[0] == "build" for call in self.docker_calls)
            second = build(self.state, self.harness)
            self.assertEqual(first, second)
            self.assertEqual(builds, sum(call[0] == "build" for call in self.docker_calls))
            self.assertEqual(first["source_digest"], self.snapshot["version"])
            write_json(self.harness / "evaluation.json", {"budget": 2})
            write_json(self.harness / "verification.json", {"evaluation_id": "another-attempt"})
            self.assertEqual(first, build(self.state, self.harness))
            self.assertEqual(builds, sum(call[0] == "build" for call in self.docker_calls))
            (self.harness / "agent.py").write_text("print('new method')")
            # New method gives a distinct build; old source remains available.
            from catalyst.executable import SOURCE_EXCLUDES
            self.snapshot, _ = snapshot_directory(self.harness, exclude=SOURCE_EXCLUDES)
            changed = build(self.state, self.harness)
            self.assertNotEqual(first["id"], changed["id"])
        with patch("catalyst.executable.docker_output", return_value=json.dumps([
            {"Id": self.image, "Config": {"Labels": {"catalyst.source": "b" * 64}}}
        ])):
            with self.assertRaises(CatalystError):
                inspect_build(self.state, first["id"])

    def test_staging_same_source_creates_distinct_evaluations_on_same_image(self):
        source = self.root / "dungeness"
        source.mkdir()
        (source / "dungeness").write_text("#!/bin/sh\nexit 0\n")
        from catalyst.dungeness import write_yaml
        write_yaml(source / "services/gateway/pricing.yaml", {
            "entries": [{"provider": "openai", "upstream_id": "openai/test-model",
                         "request_models": ["explicit-test-model", "another-test-model"]}],
        })
        commit(source)
        configure(self.state, source)
        problem = self.root / "problem"
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["problem", "create", "toy", "--output", str(problem),
                                   "--repository", "https://example.org/task.git",
                                   "--commit", "f" * 40]), 0)
        record = {"id": "e" * 64, "source_digest": self.snapshot["version"],
                  "image_id": self.image, "artifact_tag": "catalyst-image:" + "a" * 64}
        with patch("catalyst.executable.inspect_build", return_value=record):
            one = prepare(self.state, problem, self.harness, 1, 10000,
                          build_id=record["id"], model="explicit-test-model")
            two = prepare(self.state, problem, self.harness, 2, 10000,
                          build_id=record["id"], model="another-test-model")
            self.assertNotEqual(one["id"], two["id"])
            self.assertEqual(one["build"], two["build"])
            self.assertEqual(subprocess.check_output(["git", "-C", str(source), "status",
                                                      "--porcelain"]), b"")
            runtime = Path(one["runtime"])
            adapter = runtime / "adapters/harbor/catalyst_executable.py"
            self.assertEqual(adapter.read_bytes(), (RUNTIME / "harbor_agent.py").read_bytes())
            (self.harness / "agent.py").write_text("print('unbuilt change')")
            with self.assertRaisesRegex(CatalystError, "changed since"):
                prepare(self.state, problem, self.harness, 1, 10000,
                        build_id=record["id"], model="explicit-test-model")

    def test_launcher_passes_task_and_propagates_harness_exit_without_shell(self):
        spec = importlib.util.spec_from_file_location("test_launcher", RUNTIME / "launch.py")
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        task = self.root / "task.json"
        execution = self.root / "execution.json"
        write_json(task, {"workspace": str(self.root), "gateway": "http://gateway/model/openai/v1",
                          "model": "test-model"})
        write_json(execution, {"entrypoint": ["agent-command", "$(not-a-shell)"]})
        with patch.object(launcher.subprocess, "run", return_value=subprocess.CompletedProcess([], 7)) as run:
            self.assertEqual(launcher.launch(task, execution), 7)
        self.assertEqual(run.call_args.args[0], ["agent-command", "$(not-a-shell)"])
        env = run.call_args.kwargs["env"]
        self.assertEqual(env["CATALYST_TASK"], str(task.resolve()))
        self.assertEqual(env["CATALYST_MODEL"], "test-model")
        self.assertEqual(env["OPENAI_API_KEY"], "testbed")

    @unittest.skipUnless(os.environ.get("CATALYST_DUNGENESS"), "Set CATALYST_DUNGENESS for native compiler contract")
    def test_subscription_package_compiles_with_native_dungeness(self):
        source = Path(os.environ["CATALYST_DUNGENESS"])
        spec = importlib.util.spec_from_file_location("dungeness_compiler_contract",
                                                     source / "src/dungeness/compiler.py")
        compiler = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(compiler)
        model = model_profile(source, "gpt-6-astra", "openai-chatgpt")
        model["defaults"] = {"reasoning_effort": "high"}
        runtime = self.root / "runtime"
        _, paths = install_agent(runtime, {
            "id": "a" * 64, "source_digest": "b" * 64, "artifact_tag": "catalyst-image:test",
        }, model, {"model_provider": "openai-chatgpt", "reasoning_effort": "high"})
        import yaml
        folder = runtime / paths[0]
        agent = yaml.safe_load((folder / "agent.yaml").read_text())
        compiler.render_agent_dockerfile(folder / "Dockerfile", agent)
        job = yaml.safe_load(compiler.build_harbor_job("contract", agent, self.root / "task"))
        entry = job["agents"][0]
        self.assertEqual(entry["import_path"], "catalyst_executable:CatalystExecutable")
        self.assertEqual(entry["model_name"], "gpt-6-astra")
        self.assertEqual(entry["kwargs"]["reasoning_effort"], "high")
        self.assertEqual(entry["env"], {})


class DevelopmentTests(unittest.TestCase):
    def test_initial_set_has_only_the_pinned_ecdsa_problem(self):
        problems = initial_problems()
        self.assertEqual([p["id"] for p in problems], ["ecdsa.fail"])
        for problem in problems:
            self.assertRegex(problem["repository"]["commit"], r"^[0-9a-f]{40}$")
        self.assertEqual(problems[0]["candidate_paths"], ["src/point_add"])

    def test_candidate_changes_and_caches_survive_but_contract_edits_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            (workspace / ".gitignore").write_text("cache/\n")
            (workspace / "candidate").mkdir()
            (workspace / "candidate/code").write_text("initial")
            (workspace / "verifier.py").write_text("trusted")
            sha = commit(workspace)
            problem = {"repository": {"commit": sha}, "candidate_paths": ["candidate"]}
            (workspace / "candidate/code").write_text("improvement")
            (workspace / "candidate/new").write_text("new method")
            (workspace / "cache").mkdir()
            (workspace / "cache/artifact").write_text("reuse me")
            validate_workspace(problem, workspace)
            self.assertEqual((workspace / "cache/artifact").read_text(), "reuse me")
            (workspace / "verifier.py").write_text("tampered")
            with self.assertRaisesRegex(CatalystError, "Trusted problem"):
                validate_workspace(problem, workspace)

    def test_ecdsa_check_removes_stale_score_even_when_verification_fails(self):
        problem = initial_problems()[0]
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            score = workspace / problem["score_path"]
            score.write_text('{"score": 1}')
            with patch("catalyst.problems.validate_workspace"), \
                    patch("catalyst.problems.subprocess.run", return_value=subprocess.CompletedProcess([], 3)) as run, \
                    redirect_stdout(io.StringIO()):
                self.assertEqual(develop(problem["id"], workspace, "check"), 3)
            self.assertFalse(score.exists())
            self.assertEqual(run.call_args.args[0], ["bash", "./benchmark.sh"])


if __name__ == "__main__":
    unittest.main()
