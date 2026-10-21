"""Controller behavior without paid inference or challenge-specific solutions."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/evox-codex"
sys.path.insert(0, str(EXAMPLE))
import population as pop
spec = importlib.util.spec_from_file_location("evox_codex_agent", EXAMPLE / "agent.py")
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)
sys.path.pop(0)


class PopulationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.candidate = self.root / "candidate"
        self.candidate.mkdir()
        self.file = self.candidate / "source.txt"
        self.file.write_text("initial")
        self.state = self.root / "state"
        self.state.mkdir()
        self.task = {"workspace": str(self.root), "candidate_paths": ["candidate"]}

    def check(self, score, direction="minimize", valid=True):
        process = subprocess.CompletedProcess([], 0, json.dumps({"status": "ok", "score": score, "valid": valid}), "")
        with patch.object(pop.subprocess, "run", return_value=process):
            return pop.check(self.task, self.state, direction)

    def test_population_keeps_alternatives_but_restores_best(self):
        self.check(10)
        self.file.write_text("alternative")
        self.check(20)
        self.file.write_text("broken")
        self.check(1, valid=False)
        self.assertEqual(len(pop.read(self.state)["candidates"]), 2)
        self.assertEqual(pop.restore(self.task, self.state)["score"], 10)
        self.assertEqual(self.file.read_text(), "initial")
        parent, _ = pop.select(self.state, {"parent_rule": "best", "inspirations": 1})
        parent, inspiration = pop.select(self.state, {"parent_rule": "least_used", "inspirations": 1})
        self.assertEqual(parent["score"], 20)
        self.assertEqual(inspiration[0]["score"], 10)

    def test_duplicate_does_not_recheck_and_direction_cannot_change(self):
        self.check(10)
        with patch.object(pop.subprocess, "run") as run:
            self.assertTrue(pop.check(self.task, self.state, "minimize")["duplicate"])
            run.assert_not_called()
        with self.assertRaises(ValueError):
            self.check(20, "maximize")

    def test_bad_scores_timeout_and_unsafe_files_preserve_candidate(self):
        self.check(10)
        for score in (True, float("nan"), float("inf"), "1"):
            self.file.write_text(str(score))
            self.assertFalse(self.check(score)["valid"])
        with patch.object(pop.subprocess, "run", side_effect=subprocess.TimeoutExpired("evaluate", 1)):
            self.assertFalse(pop.check(self.task, self.state, "minimize")["valid"])
        self.assertEqual(pop.restore(self.task, self.state)["score"], 10)
        (self.candidate / "link").symlink_to(self.root)
        with self.assertRaises(ValueError):
            self.check(1)

    def test_strategy_validation_and_budget(self):
        policy = {"parent_rule": "best", "operator": "refine", "direction": "minimize",
                  "inspirations": 2, "rationale": "evidence", "instructions": "experiment"}
        self.assertEqual(pop.validate_strategy(policy), policy)
        for update in ({"operator": "execute_python"}, {"inspirations": True}, {"direction": "maximize"}):
            with self.assertRaises(ValueError):
                pop.validate_strategy({**policy, **update}, "minimize")
        self.assertTrue(agent.stop_for_budget({"remaining": {"normalized_usd": 0.1}}))
        self.assertTrue(agent.stop_for_budget({"remaining": {"model_tokens": 100}}))
        self.assertFalse(agent.stop_for_budget({}))

    def test_controller_evolves_strategy_on_stagnation_and_retains_best(self):
        task = {**self.task, "gateway": "http://127.0.0.1:9/v1", "gateway_auth": "placeholder",
                "model": "synthetic", "instruction": "Synthetic task; minimize score.", "limits": {"max_seconds": 2700}}
        task_file = self.root / "task.json"
        task_file.write_text(json.dumps(task))
        turns = []

        def codex(task, state, gateway, prompt, label, seconds, parent="none", schema=False):
            turns.append(label)
            final = state / "final.txt"
            if schema:
                final.write_text(json.dumps({"parent_rule": "least_used", "operator": "restructure",
                    "inspirations": 1, "direction": "minimize", "rationale": "stagnation", "instructions": "try a new approach"}))
            else:
                self.file.write_text(label)
                process = subprocess.CompletedProcess([], 0, '{"status":"ok","score":10}', '')
                with patch.object(pop.subprocess, "run", return_value=process):
                    pop.check(task, state, "minimize")
            return 0, final

        def usage(task):
            return {"remaining": {"normalized_usd": 0 if len(turns) >= 8 else 20}}

        with patch.dict(os.environ, {"CATALYST_TASK": str(task_file)}), \
             patch.object(agent, "run_codex", side_effect=codex), \
             patch.object(agent, "usage", side_effect=usage), patch.object(agent, "emit"):
            agent.main()
        self.assertIn("strategy-05", turns)
        state = next(self.root.glob(".evox-codex-*"))
        self.assertEqual(self.file.read_text(), "solution-00")
        self.assertEqual(len(json.loads((state / "strategy-history.json").read_text())), 2)
        self.assertTrue((state / "summary.json").is_file())


if __name__ == "__main__":
    unittest.main()
