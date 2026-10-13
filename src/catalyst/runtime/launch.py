"""Trusted in-container launcher for catalyst-exec-v1 (standard library only)."""
import json
import os
from pathlib import Path
import subprocess
import sys


def launch(task_file, execution_file="/opt/catalyst/execution.json"):
    task_file = str(Path(task_file).resolve())
    task = json.loads(Path(task_file).read_text())
    execution = json.loads(Path(execution_file).read_text())
    environment = dict(os.environ)
    environment.update(
        CATALYST_TASK=task_file,
        CATALYST_WORKSPACE=task["workspace"],
        CATALYST_MODEL=task.get("model") or "",
        CATALYST_MODELS=json.dumps(task.get("models", [])),
    )
    # The gateway placeholder is public. Raw upstream credentials never belong here.
    if task.get("gateway"):
        environment["OPENAI_BASE_URL"] = task["gateway"]
        if task.get("model_provider") == "openai-chatgpt" and task.get("gateway_auth") != "placeholder":
            environment.pop("OPENAI_API_KEY", None)
        else:
            environment["OPENAI_API_KEY"] = "testbed"
    result = subprocess.run(execution["entrypoint"], cwd=task["workspace"], env=environment)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(launch(sys.argv[1]))
