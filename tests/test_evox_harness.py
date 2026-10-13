"""ECDSA adapter contracts, plus an optional real upstream EvoX search test."""
import base64
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from catalyst.cheat_filter import screen
from catalyst.common import open_bundle
from catalyst.remote import request_body

ROOT = Path(__file__).resolve().parents[1] / "harnesses/ecdsa-evox"


def load_adapter():
    spec = importlib.util.spec_from_file_location("catalyst_evox_evaluator", ROOT / "evaluator.py")
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    return adapter


def task(root):
    candidate = root / "src/point_add"
    candidate.mkdir(parents=True)
    (candidate / "mod.rs").write_text("baseline")
    return {"workspace": str(root), "candidate_paths": ["src/point_add"],
            "instruction": "Optimize the ECDSA implementation.",
            "models": [{"provider": "kimi-code", "name": "k3",
                        "base_url": "http://gateway:8080/model/kimi-code/v1"}]}


class EvoxHarnessTests(unittest.TestCase):
    def test_package_has_pinned_framework_and_no_credentials(self):
        body = request_body(ROOT, "https://example.invalid")
        _, files = open_bundle(base64.b64decode(body["source"]["archive_base64"]))
        self.assertEqual(screen(files, "harness")["status"], "passed")
        self.assertEqual(body["evaluation"]["model"], {"provider": "kimi-code", "name": "k3"})
        self.assertEqual(body["evaluation"]["max_model_credits"], 3)
        self.assertIn(b"0d932b690670a7e544388ad362e9876c8bd256a0", files["Dockerfile"])

    def test_candidate_validation_rejects_traversal_aliases_and_non_rust(self):
        adapter = load_adapter()
        for name in ("../mod.rs", "/mod.rs", "./mod.rs", "a//b.rs", "a\\b.rs", "a.py"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                adapter.decode_candidate(json.dumps({"edits": [{"path": name, "old": "a", "new": "b"}]}))
        for value in ([], {"edits": {}}, {"edits": [{"path": "mod.rs", "old": "", "new": "b"}]}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                adapter.decode_candidate(json.dumps(value))

    def test_edits_use_original_source_and_reject_ambiguous_or_overlapping_matches(self):
        adapter = load_adapter()
        original = {"mod.rs": "abcdef"}
        edits = [{"path": "mod.rs", "old": "ab", "new": "c"},
                 {"path": "mod.rs", "old": "ef", "new": "X"}]
        self.assertEqual(adapter.apply_edits(original, edits), {"mod.rs": "ccdX"})
        self.assertEqual(original, {"mod.rs": "abcdef"})
        for edits in (
            [{"path": "missing.rs", "old": "a", "new": "b"}],
            [{"path": "mod.rs", "old": "abc", "new": "b"},
             {"path": "mod.rs", "old": "bc", "new": "c"}],
        ):
            with self.assertRaises(ValueError):
                adapter.apply_edits(original, edits)
        with self.assertRaises(ValueError):
            adapter.apply_edits({"mod.rs": "aaa"}, [{"path": "mod.rs", "old": "aa", "new": "b"}])

    def test_only_verified_improvements_replace_complete_candidate(self):
        adapter = load_adapter()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            context = task(root)
            (root / "src/point_add/old.rs").write_text("old")
            evaluator = adapter.CandidateEvaluator(context)
            proposal = root / "proposed.json"
            proposal.write_text(json.dumps({"edits": [
                {"path": "mod.rs", "old": "baseline", "new": "improved"}]}))
            with patch.object(adapter, "verify", return_value={"status": "ok", "score": 100}):
                evaluator.initialize()
            for result in ({"status": "failed", "score": 1}, {"status": "ok", "score": 200},
                           {"status": "ok", "score": float("nan")}, {"status": "ok", "score": True}):
                with patch.object(adapter, "verify", return_value=result):
                    evaluator.evaluate(proposal)
                self.assertEqual((evaluator.candidate / "mod.rs").read_text(), "baseline")
            with patch.object(adapter, "verify", return_value={"status": "ok", "score": 50}):
                self.assertEqual(evaluator.evaluate(proposal)["combined_score"], 2)
            self.assertEqual((evaluator.candidate / "mod.rs").read_text(), "improved")
            self.assertEqual((evaluator.candidate / "old.rs").read_text(), "old")

    def test_large_source_is_preserved_without_requiring_full_model_rewrite(self):
        adapter = load_adapter()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            context = task(root)
            original = "baseline\n" + "// preserved source\n" * 20000
            (root / "src/point_add/mod.rs").write_text(original)
            evaluator = adapter.CandidateEvaluator(context)
            with patch.object(adapter, "verify", return_value={"status": "ok", "score": 100}):
                evaluator.initialize()
            self.assertLessEqual(len(evaluator.context()), 30000)
            self.assertEqual(json.loads(evaluator.seed.read_text()), {"edits": []})
            files = adapter.apply_edits(evaluator.original, [
                {"path": "mod.rs", "old": "baseline", "new": "improved"}])
            self.assertEqual(files["mod.rs"], original.replace("baseline", "improved", 1))

    @unittest.skipUnless(os.environ.get("CATALYST_SKYDISCOVER"),
                         "Set CATALYST_SKYDISCOVER to the pinned upstream checkout.")
    def test_real_evox_loop_routes_every_model_through_declared_gateway(self):
        # The framework, SDK, search algorithm and adapter are real. Only network
        # transport and trusted-verifier output are synthetic; no sockets or money.
        import httpx
        import openai
        source = Path(os.environ["CATALYST_SKYDISCOVER"]).resolve()
        sys.path.insert(0, str(source))
        self.addCleanup(sys.path.remove, str(source))
        adapter = load_adapter()
        with patch.dict(sys.modules, {"evaluator": adapter}):
            spec = importlib.util.spec_from_file_location("catalyst_evox_agent", ROOT / "agent.py")
            agent = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(agent)
        calls = []

        def provider(request):
            self.assertEqual(str(request.url), "http://gateway:8080/model/kimi-code/v1/chat/completions")
            self.assertEqual(request.headers["authorization"], "Bearer testbed")
            body = json.loads(request.content)
            self.assertEqual(body["model"], "k3")
            self.assertFalse(any(message["role"] == "system" and not message["content"]
                                 for message in body["messages"]))
            self.assertNotIn("temperature", body)
            self.assertNotIn("max_tokens", body)
            self.assertIn("max_completion_tokens", body)
            calls.append(body)
            content = '```json\n{"edits":[{"path":"mod.rs","old":"baseline","new":"improved"}]}\n```'
            if "EvolvedProgramDatabase" in body["messages"][0]["content"]:
                strategy = (source / "skydiscover/optimize/search/evox/database/initial_search_strategy.py").read_text()
                content = "```python\n" + strategy + "\n```"
            return httpx.Response(200, json={
                "id": "synthetic", "object": "chat.completion", "created": 0, "model": "k3",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
            })

        original = openai.OpenAI
        clients = []

        def client(**kwargs):
            transport = httpx.Client(transport=httpx.MockTransport(provider))
            clients.append(transport)
            return original(**kwargs, http_client=transport)

        def verifier(path):
            return {"status": "ok", "score": 50 if (path / "mod.rs").read_text() == "improved" else 100}

        try:
            with tempfile.TemporaryDirectory() as temporary, \
                    patch("openai.OpenAI", side_effect=client), \
                    patch.object(adapter, "verify", side_effect=verifier):
                context = task(Path(temporary))
                result = agent.run(context, iterations=3)
                self.assertEqual(result["best_verified_score"], 50)
                self.assertEqual(result["search_score"], 2)
                self.assertEqual((Path(temporary) / "src/point_add/mod.rs").read_text(), "improved")
                self.assertGreaterEqual(len(calls), 4)
                self.assertTrue(any(body["max_completion_tokens"] == 1 for body in calls))
                self.assertTrue(any("EvolvedProgramDatabase" in body["messages"][0]["content"]
                                    for body in calls), "Expected actual search-strategy generation.")
        finally:
            for transport in clients:
                transport.close()
