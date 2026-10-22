"""Runtime compatibility must survive internal refactors and fail closed."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from catalyst.common import CatalystError
from catalyst.runtime_contract import require_capabilities
from catalyst.challenge.preparation import require_problem_service_runtime


class RuntimeContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "runtime-contract.json"

    def declare(self, capabilities):
        self.path.write_text(json.dumps({
            "schema_version": 1, "runtime": "dungeness", "capabilities": capabilities,
        }))

    def test_public_contract_requires_no_internal_source_paths(self):
        self.declare(["assigned-problem-service-v1", "optional-model-token-limit-v1", "future-feature-v2"])
        with patch("catalyst._legacy_dungeness.supports", side_effect=AssertionError("source probe")):
            require_problem_service_runtime(self.root)
            require_capabilities(self.root, "optional-model-token-limit-v1")
        self.assertEqual(list(self.root.iterdir()), [self.path])

    def test_missing_declared_feature_does_not_fall_back_to_legacy_code(self):
        self.declare([])
        (self.root / "dungeness").write_text("--no-model-token-limit")
        with self.assertRaisesRegex(CatalystError, "optional-model-token-limit-v1"):
            require_capabilities(self.root, "optional-model-token-limit-v1")

    def test_invalid_contract_never_uses_legacy_detection(self):
        for document in (
            "{", "[]", '{"schema_version": 2}',
            json.dumps({"schema_version": True, "runtime": "dungeness", "capabilities": []}),
            json.dumps({"schema_version": 1, "runtime": "other", "capabilities": []}),
            json.dumps({"schema_version": 1, "runtime": "dungeness", "capabilities": [1]}),
            json.dumps({"schema_version": 1, "runtime": "dungeness", "capabilities": ["x", "x"]}),
        ):
            with self.subTest(document=document):
                self.path.write_text(document)
                with patch("catalyst._legacy_dungeness.supports", side_effect=AssertionError("source probe")):
                    with self.assertRaises(CatalystError):
                        require_capabilities(self.root, "optional-model-token-limit-v1")

    def test_old_pins_remain_supported_only_when_contract_is_absent(self):
        (self.root / "dungeness").write_text("--no-model-token-limit")
        require_capabilities(self.root, "optional-model-token-limit-v1")
        with self.assertRaisesRegex(CatalystError, "command-harness-v1"):
            require_capabilities(self.root, "command-harness-v1")
        self.assertFalse(self.path.exists())

    def test_unreadable_or_dangling_contract_fails_closed(self):
        self.path.mkdir()
        with self.assertRaises(CatalystError):
            require_capabilities(self.root, "optional-model-token-limit-v1")
        self.path.rmdir()
        self.path.symlink_to(self.root / "missing")
        with patch("catalyst._legacy_dungeness.supports", side_effect=AssertionError("source probe")):
            with self.assertRaises(CatalystError):
                require_capabilities(self.root, "optional-model-token-limit-v1")
