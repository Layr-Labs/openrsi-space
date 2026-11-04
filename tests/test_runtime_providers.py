"""Runtime provider discovery fails closed and cannot be overwritten by a harness."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from openrsi_space.common import OpenRSIError
from openrsi_space.integrations.dungeness.providers import model_providers, require_model_providers
from openrsi_space.integrations.dungeness.agent import install_agent
from openrsi_space.credentials import validate_provider_access
from openrsi_space.cli import build_parser


class RuntimeProviderTests(unittest.TestCase):
    def test_discovery_uses_selected_cli_without_forwarding_credentials(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "dungeness").write_text(
                'import os, sys, json\n'
                'assert sys.argv[1:] == ["providers"]\n'
                'assert "PROVIDER_SECRET" not in os.environ\n'
                'print(json.dumps({"schema_version":1,"runtime":"dungeness",'
                '"providers":["anthropic","example"]}))\n')
            with patch.dict(os.environ, {"PROVIDER_SECRET": "fixture-secret"}):
                self.assertEqual(model_providers(root), frozenset({"anthropic", "example"}))
            require_model_providers(root, [{"provider": "anthropic"}])
            with self.assertRaisesRegex(OpenRSIError, "not supported"):
                require_model_providers(root, [{"provider": "openai"}])
            for document in (None, {}, {"providers": []},
                             {"schema_version": 1, "runtime": "dungeness", "providers": ["anthropic", "anthropic"]}):
                (root / "dungeness").write_text(f"print({json.dumps(document)!r})\n")
                with self.assertRaisesRegex(OpenRSIError, "Cannot read"):
                    model_providers(root)
            (root / "dungeness").unlink()
            with self.assertRaisesRegex(OpenRSIError, "repin"):
                model_providers(root)

    def test_install_does_not_replace_runtime_registry(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            registry = root / "services/gateway/providers.json"
            registry.parent.mkdir(parents=True)
            original = b'{"schema_version":1,"providers":{}}\n'
            registry.write_bytes(original)
            _, paths = install_agent(root, {"id": "a" * 64, "source_digest": "b" * 64,
                                            "artifact_tag": "fixture:only"},
                                     {"provider": "anthropic"}, {})
            self.assertEqual(registry.read_bytes(), original)
            self.assertNotIn("services/gateway/providers.json", paths)

    def test_grok_login_is_local_only_and_raw_session_keys_are_rejected(self):
        parser, _ = build_parser()
        self.assertNotIn("--grok-auth-file", parser.format_help())
        from contextlib import redirect_stderr
        import io
        for command in (["remote", "submit", "fixture"],
                        ["remote", "renew-access", "fixture"]):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                parser.parse_args(command + ["--grok-auth-file"])
            self.assertEqual(raised.exception.code, 2)
        for provider in ("xai", "grok-subscription"):
            with self.assertRaises(OpenRSIError):
                validate_provider_access({provider: "synthetic-token"})
        args = parser.parse_args(['local', 'run', 'fixture', '--dungeness', '.', '--grok-auth-file'])
        self.assertTrue(args.grok_auth_file.endswith('/.grok/auth.json'))
