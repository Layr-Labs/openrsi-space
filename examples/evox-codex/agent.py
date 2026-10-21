"""Bounded Codex solution turns and stagnation-triggered strategy evolution."""
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
from urllib.parse import urlsplit
from urllib.request import urlopen

from gateway_adapter import compatible_gateway
from population import best, check, describe, read, restore, select, validate_strategy

HERE = Path(__file__).resolve().parent
WINDOW = 3


def emit(event, **fields):
    print(json.dumps({"event": event, **fields}), flush=True)


def usage(task):
    url = urlsplit(task["gateway"])
    try:
        with urlopen(f"{url.scheme}://{url.netloc}/status", timeout=5) as response:
            value = json.loads(response.read(65536))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def stop_for_budget(status):
    remaining = status.get("remaining", {})
    usd = remaining.get("normalized_usd")
    tokens = remaining.get("model_tokens")
    return ((type(usd) in (int, float) and usd <= 0.5)
            or (type(tokens) in (int, float) and tokens <= 30000))


def progress(before, after, direction):
    if after is None:
        return 0.0
    if before is None:
        return 1.0
    delta = before - after if direction == "minimize" else after - before
    return delta / max(abs(before), 1)


def run_codex(task, state, gateway, prompt, label, seconds, parent="none", schema=False):
    settings = {
        "model_provider": "dungeness",
        "model_reasoning_effort": task.get("reasoning_effort") or "high",
        "model_context_window": 1050000,
        "web_search": "disabled",
        "model_providers.dungeness.name": "Dungeness",
        "model_providers.dungeness.base_url": gateway,
        "model_providers.dungeness.wire_api": "responses",
        "model_providers.dungeness.env_key": "OPENAI_API_KEY",
        "model_providers.dungeness.requires_openai_auth": False,
        "model_providers.dungeness.supports_websockets": False,
    }
    final = state / f"{label}.final.txt"
    command = ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", "--skip-git-repo-check",
               "--model", task["model"], "--json", "--enable", "unified_exec", "--disable", "apps",
               "--output-last-message", str(final)]
    if schema:
        command += ["--output-schema", str(HERE / "strategy.schema.json")]
    for key, value in settings.items():
        command += ["-c", key + "=" + json.dumps(value)]
    command.append("-")
    home = state / "codex-home"
    home.mkdir(exist_ok=True)
    env = {**os.environ, "OPENAI_API_KEY": "testbed", "CODEX_HOME": str(home),
           "EVOX_STATE": str(state), "EVOX_PARENT": parent}
    emit("codex_turn_start", label=label, seconds=seconds)
    with (state / f"{label}.jsonl").open("w") as output, (state / f"{label}.stderr").open("w") as errors:
        proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=output, stderr=errors,
                                text=True, cwd=task["workspace"], env=env, start_new_session=True)
        try:
            proc.communicate(prompt, timeout=seconds)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.communicate()
        finally:
            # Do not leave a previous turn's background edits running in the next turn.
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    emit("codex_turn_end", label=label, exit_code=proc.returncode)
    return proc.returncode, final


def main():
    task = json.loads(Path(os.environ["CATALYST_TASK"]).read_text())
    if task.get("gateway_auth") != "placeholder":
        raise SystemExit("Gateway-owned provider credentials are required.")
    state = Path(tempfile.mkdtemp(prefix=".evox-codex-", dir=task["workspace"]))
    configured = task.get("limits", {}).get("max_seconds", 2700)
    deadline = min(time.time() + configured, float(os.environ.get("DUNGENESS_AGENT_DEADLINE_EPOCH", "inf"))) - 45
    endpoints = {key: os.environ[key] for key in (
        "CATALYST_DESCRIPTION_URL", "CATALYST_PROBLEM_URL", "CATALYST_KNOWLEDGE_BASE_URL") if os.environ.get(key)}
    common = (task["instruction"] + "\n\n" + (HERE / "workflow.md").read_text()
              + "\nAssigned resource endpoints: " + json.dumps(endpoints)
              + "\nResearch state directory: " + str(state)
              + "\nRead RESEARCH.md if present to reuse findings from earlier turns.")
    strategy = {"parent_rule": "best", "operator": "free", "inspirations": 2,
                "direction": "minimize", "rationale": "Establish a valid candidate, then learn from feedback.",
                "instructions": "Read the assigned resources, establish correctness, and test one concrete hypothesis."}
    history, window_start, failures = [], None, 0
    emit("research_started", state=str(state), model=task["model"], budget=task.get("budget"), deadline=deadline)
    try:
        with compatible_gateway(task["gateway"]) as gateway:
            for iteration in range(24):
                remaining = int(deadline - time.time())
                status = usage(task)
                emit("research_status", iteration=iteration, seconds_remaining=remaining,
                     usage=status, population=describe(read(state)))
                if remaining < 100 or stop_for_budget(status) or failures >= 2:
                    break
                parent, inspirations = select(state, strategy)
                if parent:
                    restore(task, state, parent["id"])
                seconds = min(900 if not read(state)["candidates"] else 360, remaining - 75)
                prompt = (common + f"\nSOLUTION TURN {iteration}. You have at most {seconds} seconds."
                    + "\nProduce one meaningful candidate experiment. Checkpoint intermediate valid improvements."
                    + "\nDetermine objective direction from the assigned task before your first check."
                    + "\nCurrent strategy: " + json.dumps(strategy)
                    + "\nSelected parent: " + json.dumps(parent)
                    + "\nInspiration snapshots (read-only references): " + json.dumps(inspirations)
                    + "\nObserved population and recent failures: " + json.dumps(describe(read(state)))
                    + "\nEnd by checkpointing the candidate and updating RESEARCH.md. Do not change controller state files.")
                code, _ = run_codex(task, state, gateway, prompt, f"solution-{iteration:02}", seconds,
                                    parent["id"] if parent else "none")
                failures = failures + 1 if code not in (0, -signal.SIGTERM) else 0
                data = read(state)
                if data["direction"]:
                    strategy["direction"] = data["direction"]
                    try:
                        result = check(task, state, data["direction"], f"supervisor after turn {iteration}",
                                       max(1, min(240, int(deadline - time.time()))))
                        emit("candidate_checked", **result)
                    except (OSError, ValueError) as error:
                        emit("candidate_check_error", error=str(error))
                data = read(state)
                current = best(data)
                score = current["score"] if current else None
                if (iteration + 1) % WINDOW == 0:
                    gain = progress(window_start, score, data["direction"] or strategy["direction"])
                    history.append({"strategy": dict(strategy), "relative_progress": gain,
                                    "population": describe(data), "window": iteration // WINDOW})
                    (state / "strategy-history.json").write_text(json.dumps(history, indent=2))
                    window_start = score
                    if gain < 1e-4 and deadline - time.time() > 240 and not stop_for_budget(usage(task)):
                        meta_prompt = (common + "\nSTRATEGY TURN: do not edit or evaluate the candidate."
                            + "\nUse the task and observations to revise parent selection, variation operator and inspiration count."
                            + " Return only the JSON policy required by the output schema. Preserve the objective direction."
                            + " Diagnose stagnation using score spread, parent selection counts and failed attempts."
                            + "\nCurrent population: " + json.dumps(describe(data))
                            + "\nPrevious strategy outcomes: " + json.dumps(history[-4:]))
                        meta_code, final = run_codex(task, state, gateway, meta_prompt,
                                                    f"strategy-{iteration:02}", 150, schema=True)
                        try:
                            if meta_code != 0:
                                raise ValueError("Strategy generation did not complete")
                            proposal = validate_strategy(json.loads(final.read_text()), data["direction"])
                            strategy = proposal
                            emit("strategy_updated", strategy=strategy)
                        except (OSError, ValueError, TypeError) as error:
                            emit("strategy_rejected", reason=str(error), fallback=strategy)
                if failures and stop_for_budget(usage(task)):
                    break
    finally:
        emit("best_candidate_restored", **restore(task, state))
        report = {"population": describe(read(state)), "strategy_history": history, "usage": usage(task)}
        (state / "summary.json").write_text(json.dumps(report, indent=2))
        emit("research_finished", **report)


if __name__ == "__main__":
    main()
