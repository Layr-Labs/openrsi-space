"""Run the upstream EvoX algorithm; Catalyst supplies only task/model adapters."""
import asyncio
import json
import os
from pathlib import Path

from evaluator import CandidateEvaluator, load_task

UPSTREAM_REVISION = "0d932b690670a7e544388ad362e9876c8bd256a0"


def configuration(task, iterations, context=""):
    from skydiscover.optimize.config import Config

    models = []
    for model in task["models"]:
        if model["provider"] not in {"kimi-code", "moonshot", "openai", "openrouter"}:
            raise ValueError("This example needs a gateway Chat Completions provider.")
        models.append({"name": model["name"], "api_base": model["base_url"],
                       "api_key": "testbed", "weight": 1,
                       "reasoning_effort": model.get("reasoning_effort", task.get("reasoning_effort"))})
    if not models:
        raise ValueError("A declared model is required.")
    return Config.from_dict({
        "max_iterations": iterations,
        "checkpoint_interval": 1,
        "language": "json",
        "file_suffix": ".json",
        "max_solution_length": 1024 * 1024,
        "max_parallel_iterations": 1,
        "diff_based_generation": False,
        "llm": {"models": models, "guide_models": models, "evaluator_models": models,
                "max_tokens": 12000, "timeout": 180, "retries": 0},
        # Otherwise upstream's meta-search defaults to its own public model endpoint.
        "search": {"type": "evox", "share_llm": True},
        "evaluator": {"file_suffix": ".json", "timeout": 600, "max_retries": 0,
                      "cascade_evaluation": False, "llm_as_judge": False},
        "monitor": {"enabled": False},
        "prompt": {"system_message": (
            task["instruction"] + "\n\n"
            "The solution is JSON: {\"edits\": [{\"path\": \"mod.rs\", \"old\": \"exact original text\", "
            "\"new\": \"replacement text\"}, ...]}. Each path names an existing .rs file under "
            "src/point_add. Each old string must be nonempty, unique in the ORIGINAL baseline "
            "file and edits must not overlap. Every candidate's edits apply to the original "
            "baseline, not to a parent's already edited files. Preserve useful parent edits. "
            "Unchanged files and text are retained automatically. "
            "Preserve the challenge's Rust interface and correctness. "
            "Return a complete JSON solution in a json code block. "
            "The evaluator maximizes baseline_score / verified_score; invalid solutions score zero. "
            "The actual challenge minimizes avg_toffoli * peak_qubits. "
            "Evaluation runs in the separate trusted sidecar. No internet is available. "
            "The following source excerpts are partial; propose changes supported by visible code.\n"
            + context
        )},
    })


def run(task, iterations=3):
    from skydiscover import run_discovery
    from skydiscover.optimize.llm.openai import OpenAILLM

    # Check the same SDK/model configuration before expensive circuit grading.
    # These small requests still go through the gateway and count toward the cap.
    for model in configuration(task, iterations).llm.models:
        probe = OpenAILLM(model)
        try:
            asyncio.run(probe.generate("", [{"role": "user", "content": "ping"}], max_tokens=1))
        finally:
            probe.client.close()
    evaluator = CandidateEvaluator(task)
    evaluator.initialize()
    result = run_discovery(
        evaluator=evaluator.evaluate,
        initial_program=evaluator.seed,
        config=configuration(task, iterations, evaluator.context()),
        output_dir=str(evaluator.root / "search"),
        cleanup=True,
    )
    # CandidateEvaluator promotes only independently verified improvements.
    summary = {"framework": "SkyDiscover/EvoX", "revision": UPSTREAM_REVISION,
               "search_score": result.best_score, "best_verified_score": evaluator.best_score}
    (evaluator.root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary), flush=True)
    return summary


if __name__ == "__main__":
    run(load_task(), int(os.environ.get("CATALYST_EVOX_ITERATIONS", "3")))
