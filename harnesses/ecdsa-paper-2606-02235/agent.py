"""Paper-guided Codex research; native Dungeness authentication and accounting."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parent
AUTH_FILE = Path("/run/dungeness/codex-auth/auth.json")
RAM_ROOT = Path("/dev/shm")


def check_references():
    references = ROOT / "references"
    metadata = json.loads((references / "provenance.json").read_text())
    for name in ("paper.pdf",):
        actual = hashlib.sha256((references / name).read_bytes()).hexdigest()
        if actual != metadata["sha256"][name]:
            raise SystemExit(f"Bundled reference checksum mismatch: {name}")
    return references


def make_instruction(task):
    references = check_references()
    cap = float(task["budget"]["max_usd"])
    return (
        task["instruction"]
        + "\n\n## Submitted paper research method\n\n"
        + (ROOT / "instructions.md").read_text()
        + f"\n\nRaw reference paper: {references / 'paper.pdf'}\n"
        + f"""

This run has a ${cap:g} normalized model-credit cap. Check the Dungeness
cumulative usage using the mechanism in the task instructions between attempts.
Aim to finish by ${cap * 0.85:g}, leaving headroom for the final response.
The cap is a limit, not a spending target. At a small cap, test one narrow
paper-inspired change instead of attempting an architectural rewrite.
If usage is unavailable, do not invent an estimate; finish conservatively.
Respect the task's time limit and leave time to restore the best checked source.
Keep reasoning and output concise. End with the paper section used, the exact
source change, locally checked before/after metrics, and any unresolved limitation.
If there is no checked improvement, say so and retain the starting candidate.
Do not inspect or print credentials. Only candidate paths are retained for
independent verification; your narrative does not determine the official score.
"""
    )


def run():
    task = json.loads(Path(os.environ["CATALYST_TASK"]).read_text())
    if task["model_provider"] != "openai-chatgpt":
        raise SystemExit("This harness requires the ChatGPT Codex provider.")
    instruction = make_instruction(task)
    with tempfile.TemporaryDirectory(prefix="catalyst-codex-paper-", dir=RAM_ROOT) as directory:
        home = Path(directory)
        placeholder = task.get("gateway_auth") == "placeholder"
        if not placeholder:
            shutil.copyfile(AUTH_FILE, home / "auth.json")
            (home / "auth.json").chmod(0o600)
        (home / "config.toml").write_text(
            'cli_auth_credentials_store = "file"\nmodel_provider = "dungeness"\n'
            'model_context_window = 1050000\nweb_search = "disabled"\n'
            '[model_providers.dungeness]\nname = "Dungeness ChatGPT"\n'
            f'base_url = {json.dumps(task["gateway"])}\n'
            'wire_api = "responses"\nsupports_websockets = false\n'
            + ('env_key = "OPENAI_API_KEY"\nrequires_openai_auth = false\n' if placeholder
               else 'requires_openai_auth = true\n')
        )
        environment = {**os.environ, "CODEX_HOME": directory}
        if placeholder:
            environment["OPENAI_API_KEY"] = "testbed"
        else:
            environment.pop("OPENAI_API_KEY", None)
        result = subprocess.run([
            "codex", "exec", "--dangerously-bypass-approvals-and-sandbox", "--skip-git-repo-check",
            "--model", task["model"], "--json", "--enable", "unified_exec", "--disable", "apps",
            "-c", "model_reasoning_effort=" + json.dumps(task.get("reasoning_effort") or "high"), "-",
        ], input=instruction, text=True, cwd=task["workspace"], env=environment)
        # Dungeness records usage and Catalyst verifies candidates independently,
        # including if the final model request stopped at a budget boundary.
        print(json.dumps({"event": "codex_finished", "exit_code": result.returncode}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-references", action="store_true")
    args = parser.parse_args()
    if args.check_references:
        check_references()
        print("Bundled paper checksum verified.")
    else:
        run()
