"""Provider-neutral source submission, using no sockets or model calls."""
import base64
from contextlib import redirect_stderr, redirect_stdout
from decimal import Decimal
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

from catalyst.cli import main
from catalyst.common import CatalystError, open_bundle, read_json, write_json
from catalyst.live_provider import ProviderAccess
from catalyst.remote import (
    RemoteClient, digest, evaluation_config, private_json, request_body, verification_reference,
)
from catalyst.tiers import credits


class SubmissionOptionsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "agent"
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["harness", "create", "any-agent", "--executable",
                                   "--output", str(self.source)]), 0)
        (self.source / "knowledge/paper.pdf").write_bytes(b"%PDF-offline-test-fixture")
        (self.source / "requirements.txt").write_text("example-dependency==1.0\n")
        (self.source / ".env").write_text("PRIVATE_FIXTURE=not-for-submission\n")
        self.options = {"provider": "kimi-code", "model": "k3", "budget": 3,
                        "reasoning_effort": "high"}
        environment = patch.dict(os.environ, {
            "CATALYST_EVALUATOR_URL": "https://evaluator.invalid",
            "YUKON_API_TOKEN": "offline-solver-credential",
            "CATALYST_LOCAL_TEST": "", "CATALYST_LOCAL_ECDSA": "", "GITHUB_ACTIONS": "",
        })
        environment.start()
        self.addCleanup(environment.stop)

    def body(self, **options):
        return request_body(self.source, "https://evaluator.invalid",
                            evaluation_overrides={**self.options, **options})

    def test_same_source_and_knowledge_can_select_different_models(self):
        kimi = self.body()
        openai = self.body(provider="openai", model="gpt-6-astra", budget=20)
        self.assertEqual(kimi["source"], openai["source"])
        self.assertNotEqual(digest(kimi["evaluation"]), digest(openai["evaluation"]))
        _, files = open_bundle(base64.b64decode(kimi["source"]["archive_base64"]))
        self.assertEqual(files["knowledge/paper.pdf"], b"%PDF-offline-test-fixture")
        self.assertIn("requirements.txt", files)
        self.assertIn(b"COPY . /opt/harness/", files["Dockerfile"])
        self.assertNotIn(".env", files)
        self.assertNotIn("evaluation.json", files)
        self.assertFalse((self.source / "evaluation.json").exists())
        self.assertEqual(kimi["evaluation"]["llm_access"]["grant_id"], "grant_temporary_provider")
        self.assertEqual(kimi["evaluation"]["limits"], {"max_model_tokens": 100000, "max_seconds": 900})

    def test_existing_config_can_be_overridden_without_editing_it(self):
        path = self.source / "evaluation.json"
        original = self.body()["evaluation"]
        write_json(path, original)
        result = self.body(provider="openai", model="gpt-5.6-sol", budget=1, max_tokens=1000, max_seconds=60)
        self.assertEqual(result["evaluation"]["limits"], {"max_model_tokens": 1000, "max_seconds": 60})
        self.assertEqual(read_json(path), original)
        # A provider switch without an explicit effort must not inherit Kimi's effort.
        switched = evaluation_config(path, {"provider": "openai", "model": "gpt-5.6-sol"})
        self.assertNotIn("reasoning_effort", switched["model"])

    def test_ensembles_preserve_all_models_when_budget_changes(self):
        config = self.body()["evaluation"]
        config.update(schema_version=4, models=[config["model"], {"provider": "openai", "name": "gpt-6-astra"}])
        path = self.source / "evaluation.json"
        write_json(path, config)
        self.assertEqual(evaluation_config(path, {"budget": 20})["models"], config["models"])
        with self.assertRaisesRegex(CatalystError, "ensemble"):
            evaluation_config(path, self.options)

    def test_missing_or_invalid_choices_fail_before_submission(self):
        path = self.source / "evaluation.json"
        for options in ({}, {"provider": "kimi-code", "budget": 3},
                        {**self.options, "budget": float("nan")},
                        {**self.options, "budget": 0},
                        {**self.options, "model": "unpriced-model"},
                        {**self.options, "max_tokens": -1},
                        {**self.options, "max_seconds": 0}):
            with self.subTest(options=options), self.assertRaises(CatalystError):
                evaluation_config(path, options)
        write_json(path, self.body()["evaluation"])
        with self.assertRaisesRegex(CatalystError, "together"):
            evaluation_config(path, {"provider": "openai"})

    def submit(self):
        client = RemoteClient(self.root / "state")
        identity = str(uuid.uuid4())
        calls = []

        def accept(base, route, bearer, *, document, model_token):
            self.assertEqual(route, "/evaluations")
            self.assertEqual(model_token, "offline-kimi-membership-key")
            self.assertNotIn(model_token, json.dumps(document))
            calls.append(document)
            return json.dumps({"evaluation_id": identity, "request_id": document["request_id"]}).encode()

        with patch("catalyst.remote.solver_fetch", side_effect=accept), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), \
                patch("catalyst.cli.sys.stdin", io.StringIO("offline-kimi-membership-key\n")):
            status = main(["--state", str(self.root / "state"), "remote", "submit", str(self.source),
                           "--provider", "kimi-code", "--model", "k3", "--budget", "3",
                           "--reasoning-effort", "high", "--model-token-stdin"])
        self.assertEqual(status, 0)
        self.assertEqual(len(calls), 1)
        return client, identity, calls[0]

    def test_cli_sends_private_key_and_retains_exact_settings_for_wait(self):
        client, identity, request = self.submit()
        self.assertEqual(request["evaluation"]["model"], {
            "provider": "kimi-code", "name": "k3", "reasoning_effort": "high"})
        for file in (self.root / "state").rglob("*.json"):
            self.assertNotIn("offline-kimi-membership-key", file.read_text())
        # Simulate the reference produced by a completed, validated wait.
        result = {"evaluation_id": identity, "build": {"image_digest": "sha256:" + "a" * 64}}
        reference = verification_reference(result, request)
        private_json(client.folder(identity) / "verification.json", reference)
        fresh_client = RemoteClient(self.root / "state")
        self.assertEqual(read_json(fresh_client.export_reference(identity)), reference)
        self.assertFalse((self.source / "evaluation.json").exists())
        (self.source / "knowledge/paper.pdf").write_bytes(b"%PDF-changed")
        with self.assertRaisesRegex(CatalystError, "Submission changed"):
            fresh_client.export_reference(identity)

    def test_config_changes_still_block_export_for_legacy_sessions(self):
        write_json(self.source / "evaluation.json", self.body()["evaluation"])
        client, identity, request = self.submit()
        session = client.session(identity)
        session.pop("evaluation_overrides")
        private_json(client.folder(identity) / "session.json", session)
        changed = read_json(self.source / "evaluation.json")
        changed["max_model_credits"] = 5
        write_json(self.source / "evaluation.json", changed)
        with self.assertRaisesRegex(CatalystError, "Submission changed"):
            client.export_reference(identity)

    def test_credential_file_inside_source_is_rejected_before_read_or_network(self):
        keyfile = self.source / "private-access.json"
        for flag in ("--provider-access-file", "--codex-auth-file"):
            with self.subTest(flag=flag), patch("catalyst.remote.solver_fetch") as fetch, \
                    redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
                code = main(["remote", "submit", str(self.source), "--provider", "kimi-code",
                             "--model", "k3", "--budget", "3", flag, str(keyfile)])
            self.assertEqual(code, 1)
            self.assertIn("outside the submitted source", errors.getvalue())
            fetch.assert_not_called()

    def test_kimi_membership_staging_and_credit_accounting(self):
        config = self.body()["evaluation"]
        staged = self.root / "tmpfs-fixture"
        staged.mkdir()
        context = ProviderAccess(config, "offline-kimi-membership-key")
        with patch("catalyst.live_provider.subprocess.check_output", return_value="tmpfs\n"), \
                patch("catalyst.live_provider.tempfile.mkdtemp", return_value=str(staged)):
            with context as access:
                self.assertIsNone(access.auth_file)
                self.assertEqual(access.env_file.stat().st_mode & 0o777, 0o600)
                self.assertEqual(access.env_file.read_text(),
                                 "TESTBED_KIMI_CODE_API_KEY=offline-kimi-membership-key\n")
        self.assertFalse(staged.exists())
        self.assertEqual(context.access, {})
        # Normalized benchmark credits, independent of actual subscription billing.
        self.assertEqual(credits({"input_tokens": 1000, "output_tokens": 100,
                                  "cached_read_tokens": 200, "cache_write_tokens": 0},
                                 config["model"]), Decimal("0.00396"))


if __name__ == "__main__":
    unittest.main()
