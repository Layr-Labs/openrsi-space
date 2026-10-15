"""Trusted in-container launcher for catalyst-exec-v1 (standard library only)."""
import json
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def hydrate_problem(task):
    """Fetch the server-assigned task before launching user code; fail closed."""
    service = task.get("problem_service")
    if service is None:
        return task  # Old, immutable run packages remain executable.
    if (not isinstance(service, dict) or set(service) != {"url", "sha256"}
            or service["url"] != "http://gateway:8080/task"
            or not isinstance(service["sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", service["sha256"])):
        raise ValueError("Invalid assigned problem service.")
    opener = build_opener(ProxyHandler({}), NoRedirect())
    with opener.open(Request(service["url"], headers={"Accept": "application/json"}), timeout=10) as response:
        raw = response.read(256 * 1024 + 1)
    if len(raw) > 256 * 1024:
        raise ValueError("Assigned problem response is too large.")
    document = json.loads(raw)
    if not isinstance(document, dict):
        raise ValueError("Assigned problem response must be an object.")
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode()
    if hashlib.sha256(encoded).hexdigest() != service["sha256"]:
        raise ValueError("Assigned problem response does not match this run.")
    if (document.get("schema_version") != 1 or document.get("problem") != task["problem"]
            or document.get("candidate_paths") != task["candidate_paths"]
            or not isinstance(document.get("statement"), str)):
        raise ValueError("Assigned problem identity or candidate paths differ.")
    return {**task, "instruction": document["statement"] + "\n\n" + task.get("instruction", ""),
            "problem_document": document}


def launch(task_file, execution_file="/opt/catalyst/execution.json"):
    task_file = str(Path(task_file).resolve())
    task = hydrate_problem(json.loads(Path(task_file).read_text()))
    if task.get("problem_service"):
        # This is only the agent's local input. The server retains its immutable
        # document separately and never trusts this copy as scoring evidence.
        resolved = Path(task_file).with_name("catalyst-task.json")
        resolved.write_text(json.dumps(task))
        task_file = str(resolved)
    execution = json.loads(Path(execution_file).read_text())
    environment = dict(os.environ)
    environment.update(
        CATALYST_TASK=task_file,
        CATALYST_WORKSPACE=task["workspace"],
        CATALYST_MODEL=task.get("model") or "",
        CATALYST_MODELS=json.dumps(task.get("models", [])),
    )
    if task.get("problem_service"):
        environment["CATALYST_PROBLEM_URL"] = task["problem_service"]["url"]
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
