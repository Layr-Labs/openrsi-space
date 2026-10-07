from __future__ import annotations

from contextlib import redirect_stdout
import hashlib
from http.server import ThreadingHTTPServer
import io
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import zipfile

from catalyst.catalog import Catalog
from catalyst.cli import main, publication_bundle
from catalyst.common import (
    CatalystError, canonical, extract_bundle, make_bundle, open_bundle,
    read_json, snapshot_directory, write_json,
)
from catalyst.demo import seed
from catalyst.dungeness import configure, installation, normalize_run, prepare
from catalyst.server import handler_for


def package(kind, identity, **extra):
    document = {"schema_version": 1, "kind": kind, "id": identity, "title": identity, **extra}
    return make_bundle({f"{kind}.json": canonical(document)})


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.catalog = Catalog(self.root / "catalog")
        self.problem, content = package("problem", "problem", metric={"name": "score", "direction": "maximize"})
        self.catalog.publish(content)
        self.harness, content = package("harness", "method", agent="agent:projects/test/default")
        self.catalog.publish(content)

    def tearDown(self):
        self.temp.cleanup()

    def add_run(self, identity, points, **extra):
        document = {
            "problem": {k: self.problem[k] for k in ("id", "version")},
            "harness": {k: self.harness[k] for k in ("id", "version")},
            "metric": self.problem["document"]["metric"], "model": "model", "conditions": "fixed",
            "status": "completed", "evidence": "contributor-reported",
            "observations": [{"cost": cost, "score": score} for cost, score in points],
            "cost_known": True,
            **extra,
        }
        snapshot, content = package("run", identity, **document)
        self.catalog.publish(content)
        return snapshot

    def matrix(self, budget, **kwargs):
        return self.catalog.matrix("problem", self.problem["version"], budget, **kwargs)

    def test_budget_uses_observed_points_not_interpolation_or_future_score(self):
        self.add_run("attempt", [(1, .5), (5, .9)])
        self.assertIsNone(self.matrix(.99)["entries"][0]["score"])
        entry = self.matrix(3)["entries"][0]
        self.assertEqual((entry["score"], entry["cost"]), (.5, 1))
        self.assertEqual(self.matrix(5)["entries"][0]["score"], .9)

    def test_best_result_preserves_repeats_and_does_not_use_the_median(self):
        self.add_run("one", [(1, .3), (2, .9), (3, .6)])
        self.add_run("two", [(1, .4)])
        self.add_run("three", [(4, .99)])
        entry = self.matrix(3)["entries"][0]
        self.assertEqual(entry["score"], .9)
        self.assertEqual(entry["cost"], 2)
        self.assertEqual(entry["sample_count"], 2)
        self.assertEqual(entry["attempt_count"], 3)
        self.assertEqual(entry["range"], [.4, .9])

    def test_condition_and_model_groups_are_never_mixed(self):
        self.add_run("a", [(1, .4)])
        self.add_run("b", [(1, .9)], model="other")
        self.add_run("c", [(1, .99)], conditions="different")
        result = self.matrix(1, model="model", conditions="fixed")
        self.assertEqual(result["entries"][0]["score"], .4)
        self.assertEqual(result["models"], ["model", "other"])
        self.assertEqual(len(result["condition_options"]), 2)
        self.assertEqual(self.matrix(1, model="invalid")["entries"], [])

    def test_unknown_ancestor_cost_excludes_continuations(self):
        self.add_run("continued", [(1, .99)], cost_known=False, total_cost=None)
        self.assertIsNone(self.matrix(3)["entries"][0]["score"])

    def test_problem_revisions_do_not_mix(self):
        self.add_run("a", [(1, .4)])
        newer, content = package("problem", "problem", metric={"name": "score", "direction": "maximize"}, description="Changed objective")
        self.catalog.publish(content)
        result = self.catalog.matrix("problem", newer["version"], 3)
        self.assertEqual(result["entries"], [])

    def test_published_runs_are_immutable_and_idempotent(self):
        snapshot = self.add_run("a", [(1, .4)])
        self.add_run("a", [(1, .4)])  # Same content is safe to retry.
        self.assertEqual(len(self.catalog.list("run")), 1)
        with self.assertRaises(CatalystError):
            self.add_run("a", [(1, .9)])
        self.assertEqual(self.catalog.get("run", "a", snapshot["version"])["document"]["observations"][0]["score"], .4)

    def test_duplicate_source_records_do_not_count_as_independent_runs(self):
        self.add_run("a", [(1, .4)], source_record_sha256="identical")
        self.add_run("renamed", [(1, .4)], source_record_sha256="identical")
        self.assertEqual(self.matrix(1)["entries"][0]["sample_count"], 1)

    def test_missing_dependencies_reject_publication(self):
        self.problem = {**self.problem, "version": "a" * 64}
        with self.assertRaises(CatalystError):
            self.add_run("a", [(1, .4)])

    def test_report_is_a_concern_and_does_not_change_score(self):
        run = self.add_run("a", [(1, .4)])
        result = self.catalog.report("a", run["version"], "Failed on another problem.")
        self.assertIn("no automatic", result["status"])
        self.assertEqual(self.matrix(1)["entries"][0]["score"], .4)
        self.assertEqual(self.matrix(1)["entries"][0]["runs"][0]["report_count"], 1)

    def test_demo_crosses_rankings_at_each_ecdsa_tier_and_retains_full_curves(self):
        seed(self.catalog)
        problem = next(p for p in self.catalog.list("problem") if p["id"] == "demo-ecdsa-best")
        for budget, winner in ((20, "demo-direct"), (200, "demo-notes"), (None, "demo-planner")):
            result = self.catalog.matrix(problem["id"], problem["version"], budget)
            self.assertEqual(result["entries"][0]["id"], winner)
            self.assertTrue(result["entries"][0]["frontier"])
            self.assertTrue(all(r["document"]["evidence"] == "demo" for e in result["entries"] for r in e["runs"]))
            self.assertTrue(all(len(r["document"]["observations"]) == 4 for e in result["entries"] for r in e["runs"]))


class BundleTests(unittest.TestCase):
    def test_hashes_are_deterministic_and_tampering_is_rejected(self):
        snapshot, content = package("harness", "method", agent="default")
        self.assertEqual(content, package("harness", "method", agent="default")[1])
        buffer = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(content)) as original, zipfile.ZipFile(buffer, "w") as changed:
            for name in original.namelist():
                data = original.read(name)
                if name == "harness.json":
                    data = data.replace(b"default", b"altered")
                changed.writestr(name, data)
        with self.assertRaises(CatalystError):
            open_bundle(buffer.getvalue())

    def test_traversal_symlinks_and_secrets_are_rejected(self):
        for path in ("../escape", "/absolute", "knowledge/.env"):
            with self.assertRaises(CatalystError):
                make_bundle({"harness.json": canonical({"schema_version": 1, "kind": "harness", "id": "h", "title": "h", "agent": "a"}), path: b"x"})
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_json(root / "harness.json", {"schema_version": 1, "kind": "harness", "id": "h", "title": "h", "agent": "a"})
            (root / ".env").write_text("SECRET=hidden")
            snapshot, content = snapshot_directory(root)
            self.assertNotIn(".env", snapshot["files"])
            (root / "link").symlink_to(root / "harness.json")
            with self.assertRaises(CatalystError):
                snapshot_directory(root)

    def test_nonfinite_scores_cannot_be_published(self):
        for value in (float("inf"), float("nan")):
            with self.assertRaises((CatalystError, ValueError)):
                package("run", "run", observations=[{"score": value, "cost": 1}])


class NormalizeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.problem, _ = package("problem", "p", metric={"name": "score", "direction": "maximize"})
        self.harness, _ = package("harness", "h", agent="default")
        self.record = self.root / "record.json"
        write_json(self.record, {
            "schema_version": 1, "type": "run", "id": "raw", "namespace": "users/test",
            "relations": {}, "data": {
                "status": "completed", "metric": {"name": "score", "direction": "maximize"},
                "model": {"provider": "provider", "upstream_id": "model"},
                "usage": {"normalized_usd": 2, "billed_usd": None},
                "metrics": {"score": .7}, "configuration": {},
            },
        })
        usage = self.root / "usage"
        usage.mkdir()
        events = [
            {"source": "evaluator", "kind": "evaluation.completed",
             "data": {"status": "ok", "score": .5}, "usage": {"normalized_usd": 1}},
            {"source": "agent", "kind": "evaluation.completed",
             "data": {"status": "ok", "score": 100}, "usage": {"normalized_usd": 0}},
            {"source": "evaluator", "kind": "evaluation.completed",
             "data": {"status": "invalid", "score": 100}, "usage": {"normalized_usd": 0}},
        ]
        (usage / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events))

    def tearDown(self):
        self.temp.cleanup()

    def test_current_schema_extracts_only_successful_evaluator_events(self):
        doc = normalize_run(self.record, self.problem, self.harness)
        self.assertEqual([(p["cost"], p["score"]) for p in doc["observations"]], [(1, .5), (2, .7)])
        self.assertIsNone(doc["billed_usd"])
        self.assertEqual(doc["evidence"], "contributor-reported")
        self.assertEqual(doc["input_provenance"], "user-associated")

    def test_continuation_cost_is_added_and_unknown_ancestry_stays_unknown(self):
        doc = normalize_run(self.record, self.problem, self.harness, starting_cost=5)
        self.assertEqual(doc["total_cost"], 7)
        self.assertEqual(doc["observations"][0]["cost"], 6)
        doc = normalize_run(self.record, self.problem, self.harness, starting_cost=None)
        self.assertFalse(doc["cost_known"])
        self.assertIsNone(doc["total_cost"])
        with self.assertRaises(CatalystError):
            normalize_run(self.record, self.problem, self.harness, starting_cost=-1)

    def test_clean_verifier_score_is_used_without_sidecar(self):
        raw = json.loads(self.record.read_text())
        raw["data"].pop("metrics")
        write_json(self.record, raw)
        (self.root / "usage" / "events.jsonl").write_text("")
        final = self.root / "harbor" / "job" / "trial" / "verifier" / "score.json"
        write_json(final, {"score": .9, "valid": True})
        doc = normalize_run(self.record, self.problem, self.harness)
        self.assertEqual(doc["observations"][0]["kind"], "clean-verifier")
        self.assertEqual(doc["observations"][0]["score"], .9)
        write_json(final, {"score": 1, "valid": False})
        self.assertEqual(normalize_run(self.record, self.problem, self.harness)["observations"], [])

    def test_metric_mismatch_is_rejected(self):
        self.problem["document"]["metric"]["name"] = "other"
        with self.assertRaises(CatalystError):
            normalize_run(self.record, self.problem, self.harness)

    def test_verification_conditions_separate_but_harness_knowledge_and_model_caps_do_not(self):
        raw = read_json(self.record)
        raw["data"]["configuration"]["resolved"] = {
            "policies": {"budget": {"model": {"max_usd": 1}, "evaluation": {"submissions": 10}}},
            "evaluation": {"mode": "full-benchmark"},
            "initialization": {"knowledge_base": {"ref": "knowledge-base:one"}},
        }
        write_json(self.record, raw)
        first = normalize_run(self.record, self.problem, self.harness)["conditions"]
        raw["data"]["configuration"]["resolved"]["initialization"]["knowledge_base"]["ref"] = "knowledge-base:two"
        raw["data"]["configuration"]["resolved"]["policies"]["budget"]["model"]["max_usd"] = 5
        write_json(self.record, raw)
        self.assertEqual(normalize_run(self.record, self.problem, self.harness)["conditions"], first)
        raw["data"]["configuration"]["resolved"]["policies"]["budget"]["evaluation"]["submissions"] = 100
        write_json(self.record, raw)
        self.assertNotEqual(normalize_run(self.record, self.problem, self.harness)["conditions"], first)

    def test_raw_evidence_is_only_packaged_when_requested(self):
        target = self.root / "normalized"
        write_json(target / "run.json", normalize_run(self.record, self.problem, self.harness))
        _, files = open_bundle(publication_bundle(target, record_path=self.record))
        self.assertEqual(set(files), {"run.json"})
        _, files = open_bundle(publication_bundle(target, True, self.record))
        self.assertEqual(set(files), {"run.json", "dungeness-record.json", "trace/events.jsonl"})


class HTTPTests(unittest.TestCase):
    def test_publication_query_fetch_and_report_over_http(self):
        with tempfile.TemporaryDirectory() as temp:
            catalog = Catalog(Path(temp) / "catalog")
            seed(catalog)
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(catalog))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                catalog_response = json.loads(urlopen(base + "/api/catalog").read())
                objects = catalog_response["objects"]
                self.assertEqual(catalog_response["budget_tiers"], [20, 200, "best"])
                problem = next(o for o in objects if o["kind"] == "problem")
                matrix = json.loads(urlopen(base + f"/api/matrix?problem={problem['id']}&version={problem['version']}&budget=20").read())
                self.assertEqual(len(matrix["entries"]), 3)
                best = json.loads(urlopen(base + f"/api/matrix?problem={problem['id']}&version={problem['version']}&budget=best").read())
                self.assertIsNone(best["budget"])
                self.assertEqual(best["entries"][0]["id"], "demo-planner")
                with self.assertRaises(HTTPError) as invalid_tier:
                    urlopen(base + f"/api/matrix?problem={problem['id']}&version={problem['version']}&budget=21")
                self.assertEqual(invalid_tier.exception.code, 400)
                invalid_tier.exception.close()
                harness, content = package("harness", "uploaded", agent="default")
                response = urlopen(Request(base + "/api/publish", data=content, headers={"Content-Type": "application/zip"}))
                self.assertEqual(response.status, 201)
                fetched = urlopen(base + f"/api/bundles/harness/uploaded/{harness['version']}").read()
                self.assertEqual(open_bundle(fetched)[0], harness)
                run = matrix["entries"][0]["runs"][0]
                request = Request(base + "/api/reports", data=canonical({
                    "run_id": run["id"], "run_version": run["version"], "body": "Needs a transfer test.",
                }), headers={"Content-Type": "application/json"})
                self.assertEqual(urlopen(request).status, 201)
                detail = json.loads(urlopen(base + f"/api/objects/run/{run['id']}/{run['version']}").read())
                self.assertEqual(len(detail["reports"]), 1)
                page = urlopen(base + "/").read()
                self.assertIn(b"Find a method worth trying", page)
                with self.assertRaises(HTTPError) as caught:
                    urlopen(Request(base + "/api/reports", data=b"{}", headers={
                        "Content-Type": "application/json", "Origin": "https://unrelated.example"}))
                caught.exception.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


class AdapterTests(unittest.TestCase):
    def test_staging_is_isolated_and_pinned(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "upstream"
            source.mkdir()
            (source / "dungeness").write_text("#!/bin/sh\nexit 0\n")
            write_yaml = __import__("catalyst.dungeness", fromlist=["write_yaml"]).write_yaml
            write_yaml(source / "agents/projects/test/default/agent.yaml",
                       {"schema_version": 1, "type": "agent", "namespace": "projects/test", "id": "default"})
            subprocess.run(["git", "init", "-q", str(source)], check=True)
            subprocess.run(["git", "-C", str(source), "add", "."], check=True)
            subprocess.run(["git", "-C", str(source), "-c", "user.name=Test", "-c", "user.email=test@localhost",
                            "-c", "commit.gpgsign=false",
                            "commit", "-qm", "Fixture runtime"], check=True)
            state = root / "state"
            pinned = configure(state, source)["dungeness"]["commit"]
            args = ["--state", str(state)]
            problem = root / "problem"
            harness = root / "harness"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(args + ["problem", "create", "toy", "--output", str(problem),
                                              "--repository", "https://example.org/source.git", "--commit", "a"*40]), 0)
                self.assertEqual(main(args + ["harness", "create", "notes", "--output", str(harness),
                                              "--agent", "agent:projects/test/default"]), 0)
            (harness / "knowledge" / ".env").write_text("DO_NOT_STAGE=secret")
            meta = prepare(state, problem, harness, 1, 10000)
            runtime = Path(meta["runtime"])
            self.assertEqual(meta["dungeness_commit"], pinned)
            self.assertEqual(subprocess.check_output(["git", "-C", str(source), "status", "--porcelain"]), b"")
            self.assertEqual(subprocess.check_output(["git", "-C", str(runtime), "status", "--porcelain"]), b"")
            self.assertEqual(subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"]).decode().strip(), pinned)
            self.assertNotEqual(meta["execution_commit"], pinned)
            self.assertFalse(any(p.name == ".env" for p in (runtime / "knowledge-bases").rglob("*")))
            (source / "uncommitted").write_text("changed")
            with self.assertRaises(CatalystError):
                installation(state)

    def test_cli_roundtrip_and_harness_derivation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = ["--state", str(root / "state")]
            source, derived = root / "original", root / "derived"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(state + ["harness", "create", "original", "--output", str(source)]), 0)
                original, _ = snapshot_directory(source)
                self.assertEqual(main(state + ["harness", "create", "derived", "--from", str(source), "--output", str(derived)]), 0)
                self.assertEqual(read_json(derived / "harness.json")["derived_from"]["version"], original["version"])
                self.assertEqual(main(state + ["publish", str(source)]), 0)
                self.assertEqual(main(state + ["fetch", "harness", "original", original["version"], "--output", str(root / "fetched")]), 0)
            fetched, _ = snapshot_directory(root / "fetched")
            self.assertEqual(fetched["version"], original["version"])


if __name__ == "__main__":
    unittest.main()
