"""Trusted in-container launcher for the OpenRSI executable harness (standard library only)."""
import json
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import time
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
    library = document.get("knowledge_base")
    description_note = (
        f"\n\nAssigned problem release: {document['release']}. "
        f"Query its read-only description at {document['description_url']} "
        "for the statement, content hash, evaluation contract and knowledge-base link. "
        "Use this run's assigned release."
        if document.get("description_url") else "")
    catalog_entries = "resources" if document.get("description_url") else "papers"
    library_note = (f"\n\nShared research library: {library['url']} "
                    f"({library['count']} resources). Read the catalog's {catalog_entries} array. "
                    "Fetch relevant entries from their listed task-server URLs and use each entry's "
                    "media_type to select how to read it; resources are not necessarily PDFs. "
                    "Internet access is disabled."
                    if library else "")
    return {**task, "instruction": document["statement"] + description_note + library_note + "\n\n" + task.get("instruction", ""),
            "problem_document": document}


def check_local_toolchain(task):
    """Report agent-side Rust availability without installing or requiring it.

    This is startup feedback, not trusted evidence: the solver owns the image.
    The authoritative evaluator has its own toolchain.
    """
    workspace = Path(task["workspace"])
    pin = next((workspace / name for name in ("rust-toolchain.toml", "rust-toolchain")
                if (workspace / name).is_file()), None)
    if pin is None:
        return task
    try:
        with pin.open("rb") as stream:
            text = stream.read(4097).decode("utf-8").strip()
        if len(text) > 4096:
            return task
        if text.startswith("["):
            channel = re.search(r'''(?m)^\s*channel\s*=\s*["']([0-9]+\.[0-9]+\.[0-9]+)["']\s*(?:#.*)?$''', text)
            expected = channel[1] if channel else None
        else:
            expected = text
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", expected):
            return task
    except (OSError, UnicodeError, ValueError, KeyError, TypeError):
        return task
    observed = None
    try:
        result = subprocess.run(
            ["rustc", "--version"], cwd=workspace, capture_output=True, text=True,
            timeout=10, env={**os.environ, "RUSTUP_AUTO_INSTALL": "0", "RUSTUP_TOOLCHAIN": expected},
        )
        match = re.match(r"rustc (\d+\.\d+\.\d+)\b", result.stdout or "")
        if result.returncode == 0 and match:
            observed = match[1]
    except (OSError, subprocess.TimeoutExpired):
        pass
    available = observed == expected
    report = {"tool": "rustc", "required_version": expected, "observed_version": observed,
              "status": "available" if available else "unavailable"}
    message = (f"Agent toolchain check: Rust {expected} is available. Dependencies may still be missing."
               if available else
               f"Agent toolchain check: Rust {expected} is unavailable in this container. "
               "Use evaluate for compilation and scoring through the trusted evaluator; it supplies "
               "its own toolchain and does not need Rust in the agent container. For optional "
               "agent-side compilation, install the pinned toolchain and dependencies in the "
               "harness image before running; runtime downloads "
               "are unavailable.")
    print(json.dumps({"event": "local_toolchain_check", **report, "message": message}), flush=True)
    return {**task, "local_toolchain": report,
            "instruction": task.get("instruction", "") + "\n\n" + message}


def launch(task_file, execution_file=None):
    execution_file = execution_file or Path(__file__).with_name("execution.json")
    task_file = str(Path(task_file).resolve())
    task = hydrate_problem(json.loads(Path(task_file).read_text()))
    task = check_local_toolchain(task)
    if task.get("problem_service") or task.get("local_toolchain"):
        # This is only the agent's local input. The server retains its immutable
        # document separately and never trusts this copy as scoring evidence.
        resolved = Path(task_file).with_name("openrsi-task.json")
        resolved.write_text(json.dumps(task))
        task_file = str(resolved)
    execution = json.loads(Path(execution_file).read_text())
    environment = dict(os.environ)
    # Smoke uses this launcher directly; Dungeness supplies an absolute deadline
    # on real runs, which must not be extended here.
    if "remaining_seconds" in task and "DUNGENESS_AGENT_DEADLINE_EPOCH" not in environment:
        remaining = max(0, float(task["remaining_seconds"]))
        environment["DUNGENESS_AGENT_DEADLINE_EPOCH"] = str(time.time() + remaining)
        environment["DUNGENESS_AGENT_TIMEOUT_SEC"] = str(int(remaining))
    environment.update(
        OPENRSI_TASK=task_file,
        OPENRSI_WORKSPACE=task["workspace"],
        OPENRSI_MODEL=task.get("model") or "",
        OPENRSI_MODELS=json.dumps(task.get("models", [])),
    )
    if task.get("problem_service"):
        environment["OPENRSI_PROBLEM_URL"] = task["problem_service"]["url"]
    if task.get("problem_document", {}).get("knowledge_base"):
        environment["OPENRSI_KNOWLEDGE_BASE_URL"] = task["problem_document"]["knowledge_base"]["url"]
    if task.get("problem_document", {}).get("description_url"):
        environment["OPENRSI_DESCRIPTION_URL"] = task["problem_document"]["description_url"]
        environment["OPENRSI_PROBLEM_RELEASE"] = task["problem_document"]["release"]
    # Previously submitted harnesses still read the original task variable names.
    # Only alias task metadata, never provider access or arbitrary environment keys.
    for suffix in ("TASK", "WORKSPACE", "MODEL", "MODELS", "PROBLEM_URL",
                   "KNOWLEDGE_BASE_URL", "DESCRIPTION_URL", "PROBLEM_RELEASE"):
        key = "OPENRSI_" + suffix
        if key in environment:
            environment["CATALYST_" + suffix] = environment[key]
    # The gateway placeholder is public. Raw upstream credentials never belong here.
    if task.get("gateway"):
        environment["OPENAI_BASE_URL"] = task["gateway"]
        environment["OPENAI_API_KEY"] = "testbed"
    result = subprocess.run(execution["entrypoint"], cwd=task["workspace"], env=environment)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(launch(sys.argv[1]))
