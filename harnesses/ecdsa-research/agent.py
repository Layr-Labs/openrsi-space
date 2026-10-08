"""Submitted Codex harness; Dungeness provides model access and accounting."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def run():
    task = json.loads(Path(os.environ["CATALYST_TASK"]).read_text())
    if task["model_provider"] != "openai-chatgpt":
        raise SystemExit("This harness requires the ChatGPT Codex provider.")
    instruction = task["instruction"] + """
This is a one-dollar integration research run. Spend very little reasoning and
output: inspect the point-add candidate, identify one small plausible optimization,
and make it only if you can verify it with the provided evaluate command. Keep the
original candidate when uncertain. Do not spend time on broad research. Finish
quickly with a brief account of what you inspected and changed. Do not inspect or
print credentials. Only candidate paths are retained for independent verification.
"""
    with tempfile.TemporaryDirectory(prefix="catalyst-codex-", dir="/dev/shm") as directory:
        home = Path(directory)
        shutil.copyfile("/run/dungeness/codex-auth/auth.json", home / "auth.json")
        (home / "auth.json").chmod(0o600)
        (home / "config.toml").write_text(
            'cli_auth_credentials_store = "file"\nmodel_provider = "dungeness"\n'
            'model_context_window = 1050000\nweb_search = "disabled"\n'
            '[model_providers.dungeness]\nname = "Dungeness ChatGPT"\n'
            f'base_url = {json.dumps(task["gateway"])}\n'
            'wire_api = "responses"\nrequires_openai_auth = true\nsupports_websockets = false\n')
        environment = {**os.environ, "CODEX_HOME": directory}
        environment.pop("OPENAI_API_KEY", None)
        result = subprocess.run([
            "codex", "exec", "--dangerously-bypass-approvals-and-sandbox", "--skip-git-repo-check",
            "--model", task["model"], "--json", "--enable", "unified_exec", "--disable", "apps",
            "-c", 'model_reasoning_effort=' + json.dumps(task.get("reasoning_effort") or "high"), "-",
        ], input=instruction, text=True, cwd=task["workspace"], env=environment)
        # The worker obtains usage and verification independently, including if
        # Dungeness stopped the final model request on its budget boundary.
        print(json.dumps({"event": "codex_finished", "exit_code": result.returncode}), flush=True)


if __name__ == "__main__":
    run()
