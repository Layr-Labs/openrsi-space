"""Keep shared contracts usable by the verifier without client/execution imports."""
import ast
import importlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import openrsi_space
from openrsi_space.client import evaluations, transport
from openrsi_space.contracts import evaluation, results


class ModuleBoundaryTests(unittest.TestCase):
    def test_contracts_have_no_client_or_execution_dependency(self):
        root = Path(openrsi_space.__file__).parent
        forbidden = ("openrsi_space.client", "openrsi_space.cli", "openrsi_space.integrations",
                     "openrsi_space.harnesses", "openrsi_space.challenge", "openrsi_space.remote",
                     "openrsi_space.executable", "openrsi_space.local", "subprocess", "urllib.request")
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
                self.assertIs(importlib.import_module("openrsi_space." + old),
                              importlib.import_module("openrsi_space." + new))
        remote = importlib.import_module("openrsi_space.remote")
        self.assertIs(remote.validate_evaluation_config, evaluation.validate_evaluation_config)
        self.assertIs(remote.judgment, results.judgment)
        self.assertIs(remote.RemoteClient, evaluations.RemoteClient)

    def test_existing_transport_overrides_reach_relocated_client(self):
        remote = importlib.import_module("openrsi_space.remote")
        original = transport.endpoint
        with tempfile.TemporaryDirectory() as directory:
            with patch("openrsi_space.remote.endpoint", return_value="http://localhost:1234") as endpoint:
                client = remote.RemoteClient(Path(directory), bearer="synthetic-token")
                self.assertEqual(client.base, "http://localhost:1234")
                endpoint.assert_called_once_with()
        self.assertIs(transport.endpoint, original)
        self.assertIs(remote.endpoint, original)
