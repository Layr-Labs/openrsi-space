"""Public installation and credential handoff must not require private code."""
from contextlib import redirect_stdout
import ast
import base64
import importlib
import io
import json
from pathlib import Path
import pkgutil
import tempfile
import tomllib
import unittest

import catalyst
from catalyst.cli import main
from catalyst.credentials import encode_codex_access, PREFIX


PRIVATE_MODULES = {
    "artifact_storage", "artifacts", "cheat_filter", "dungeness", "ecdsa_history",
    "evaluator", "github_identity", "hosted", "live_provider", "local_run",
    "model_access", "pricing", "service", "solution_corpus", "source_audit",
    "worker", "yukon_auth", "yukon_binding", "catalog", "server", "demo", "templates",
}


class PublicBoundaryTests(unittest.TestCase):
    def test_version_exits_successfully_without_requiring_a_command(self):
        with redirect_stdout(io.StringIO()) as output, self.assertRaises(SystemExit) as result:
            main(["--version"])
        self.assertEqual(result.exception.code, 0)
        self.assertEqual(output.getvalue().strip(), f"catalyst {catalyst.__version__}")
        project = Path(__file__).resolve().parents[1] / "pyproject.toml"
        self.assertEqual(catalyst.__version__, tomllib.loads(project.read_text())["project"]["version"])

    def test_public_package_has_no_private_runtime_or_imports(self):
        root = Path(catalyst.__file__).parent
        names = {item.name for item in pkgutil.iter_modules(catalyst.__path__)}
        self.assertFalse(names & PRIVATE_MODULES)
        self.assertFalse((root / "local_fixture").exists())
        for name in names:
            importlib.import_module("catalyst." + name)
        for path in root.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ImportFrom):
                    self.assertFalse((node.module or "").startswith("catalyst_verifier"), path)
                    if node.level:
                        package = ".".join(("catalyst", *path.relative_to(root).parts[:-1]))
                        resolved = importlib.util.resolve_name("." * node.level + (node.module or ""), package)
                        if resolved.startswith("catalyst."):
                            self.assertNotIn(resolved.split(".")[1], PRIVATE_MODULES, path)
                elif isinstance(node, ast.Import):
                    self.assertFalse(any(alias.name.startswith("catalyst_verifier") for alias in node.names), path)

    def test_public_cli_exposes_solver_commands_not_operator_commands(self):
        from catalyst.cli import build_parser
        _, commands = build_parser()
        self.assertTrue({"remote", "yukon-run", "yukon-submit", "problem", "harness"} <= set(commands.choices))
        self.assertTrue({"worker", "evaluator-serve", "artifact-sync", "maintenance",
                         "github-configure", "evaluate", "init", "serve", "demo", "publish",
                         "fetch", "report", "list"}.isdisjoint(commands.choices))

    def test_starter_and_problem_lookup_work_with_public_package(self):
        with tempfile.TemporaryDirectory() as temporary, redirect_stdout(io.StringIO()) as output:
            target = Path(temporary) / "agent"
            self.assertEqual(main(["harness", "create", "agent", "--executable", "--output", str(target)]), 0)
            document = json.loads((target / "harness.json").read_text())
            self.assertEqual(document["execution"]["interface"], "catalyst-exec-v1")
            self.assertTrue((target / "agent.py").is_file())
            self.assertEqual(main(["problem", "list"]), 0)
            self.assertIn("ecdsa.fail", output.getvalue())

    def test_only_temporary_subscription_access_is_encoded(self):
        document = {"auth_mode": "chatgpt", "last_refresh": "2026-10-14T00:00:00Z",
                    "tokens": {"access_token": "synthetic-access", "id_token": "synthetic-id",
                               "account_id": "synthetic-account", "refresh_token": "must-remain-local"}}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "auth.json"
            path.write_text(json.dumps(document))
            original = path.read_bytes()
            encoded = encode_codex_access(path)
            decoded = json.loads(base64.urlsafe_b64decode(encoded[len(PREFIX):]))
            self.assertEqual(set(decoded), {"access_token", "id_token", "account_id", "last_refresh"})
            self.assertNotIn("must-remain-local", json.dumps(decoded))
            self.assertEqual(path.read_bytes(), original)
