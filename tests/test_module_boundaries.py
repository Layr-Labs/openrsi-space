"""Keep shared contracts usable by the verifier without client/execution imports."""
import ast
import importlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import catalyst
from catalyst.client import evaluations, transport
from catalyst.contracts import evaluation, results


class ModuleBoundaryTests(unittest.TestCase):
    def test_contracts_have_no_client_or_execution_dependency(self):
        root = Path(catalyst.__file__).parent
        forbidden = ("catalyst.client", "catalyst.cli", "catalyst.integrations",
                     "catalyst.harnesses", "catalyst.challenge", "catalyst.remote",
                     "catalyst.executable", "catalyst.local", "subprocess", "urllib.request")
        # Include shared helpers because importing them must not pull execution in.
        paths = list((root / "contracts").glob("*.py")) + [root / "common.py"]
        for path in paths:
            for node in ast.walk(ast.parse(path.read_text())):
                names = ([item.name for item in node.names] if isinstance(node, ast.Import)
                         else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
                for name in names:
                    with self.subTest(path=path.name, dependency=name):
                        self.assertFalse(any(name == prefix or name.startswith(prefix + ".")
                                             for prefix in forbidden))

    def test_old_imports_resolve_to_canonical_implementations(self):
        for old, new in {
            "tiers": "contracts.accounting", "executable": "harnesses.executable",
            "harness_catalog": "client.catalog", "local": "integrations.dungeness.local",
            "agent_setup": "integrations.dungeness.agent",
            "runtime_contract": "integrations.dungeness.runtime_contract",
            "_legacy_dungeness": "integrations.dungeness.legacy",
            "yukon": "integrations.yukon.authentication",
            "yukon_submit": "integrations.yukon.submission", "receipts": "integrations.yukon.receipts",
        }.items():
            with self.subTest(module=old):
                self.assertIs(importlib.import_module("catalyst." + old),
                              importlib.import_module("catalyst." + new))
        remote = importlib.import_module("catalyst.remote")
        self.assertIs(remote.validate_evaluation_config, evaluation.validate_evaluation_config)
        self.assertIs(remote.judgment, results.judgment)
        self.assertIs(remote.RemoteClient, evaluations.RemoteClient)

    def test_existing_transport_overrides_reach_relocated_client(self):
        remote = importlib.import_module("catalyst.remote")
        original = transport.endpoint
        with tempfile.TemporaryDirectory() as directory:
            with patch("catalyst.remote.endpoint", return_value="http://localhost:1234") as endpoint:
                client = remote.RemoteClient(Path(directory), bearer="synthetic-token")
                self.assertEqual(client.base, "http://localhost:1234")
                endpoint.assert_called_once_with()
        self.assertIs(transport.endpoint, original)
        self.assertIs(remote.endpoint, original)
