"""Executable source packages and local Docker builds.

The same functions can run on a dedicated worker. Local builds are not official
evidence, and this module does not accept provider credentials.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import uuid

from .common import (
    CatalystError, canonical, extract_bundle, now, read_json, safe_relative,
    snapshot_directory, version_id, write_json,
)

INTERFACE = "catalyst-exec-v1"
RUNTIME = Path(__file__).parent / "runtime"
IMAGE_RE = re.compile(r"sha256:[0-9a-f]{64}")
# Runtime policy and remote result references are not executable build inputs.
SOURCE_EXCLUDES = frozenset({"evaluation.json", "verification.json"})


def validate_execution(execution: dict) -> None:
    if not isinstance(execution, dict) or execution.get("interface") != INTERFACE:
        raise CatalystError(f"Executable harnesses require interface {INTERFACE}.")
    if set(execution) != {"interface", "dockerfile", "entrypoint"}:
        raise CatalystError("execution requires only interface, dockerfile, and entrypoint.")
    if not isinstance(execution["dockerfile"], str):
        raise CatalystError("dockerfile must be a relative filename.")
    safe_relative(execution["dockerfile"])
    argv = execution["entrypoint"]
    if (not isinstance(argv, list) or not argv or len(argv) > 64
            or any(not isinstance(item, str) or not item or "\0" in item for item in argv)):
        raise CatalystError("entrypoint must be a nonempty command argument list.")


def create_starter(target: Path) -> dict:
    """Add editable source; problem toolchains belong in the solver's Dockerfile."""
    (target / "Dockerfile").write_text(
        "FROM python:3.12-slim-bookworm\n"
        "COPY agent.py /opt/harness/agent.py\n"
        "WORKDIR /workspace/repo\n"
    )
    (target / "agent.py").write_text(
        '"""Replace this baseline with your autonomous solver. No model calls yet."""\n'
        "import json\n"
        "import os\n"
        "from pathlib import Path\n\n"
        'task = json.loads(Path(os.environ["CATALYST_TASK"]).read_text())\n'
        'workspace = Path(task["workspace"])\n'
        'assert workspace.is_dir()\n'
        'print(json.dumps({"status": "completed", "problem": task["problem"],\n'
        '                  "candidate_paths": task["candidate_paths"]}))\n'
    )
    return {"interface": INTERFACE, "dockerfile": "Dockerfile",
            "entrypoint": ["python3", "/opt/harness/agent.py"]}


def docker_output(argv: list[str], *, timeout=120) -> str:
    try:
        completed = subprocess.run(["docker", *argv], capture_output=True, text=True,
                                   timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CatalystError(f"Docker command could not complete: {error}") from error
    if completed.returncode:
        raise CatalystError(completed.stderr[-4000:] or completed.stdout[-4000:])
    return completed.stdout.strip()


def build(state: Path, harness_path: Path, *, timeout=1200) -> dict:
    snapshot, bundle = snapshot_directory(harness_path, exclude=SOURCE_EXCLUDES)
    if snapshot["kind"] != "harness":
        raise CatalystError("Build requires a harness package.")
    execution = snapshot["document"].get("execution")
    validate_execution(execution)
    if execution["dockerfile"] not in snapshot["files"]:
        raise CatalystError("The build recipe is missing from the source package.")
    # The platform's launcher is separate from editable source, but part of the build identity.
    launcher = (RUNTIME / "launch.py").read_bytes()
    architecture = docker_output(["info", "--format", "{{.OSType}}/{{.Architecture}}"])
    recipe = {"source_digest": snapshot["version"], "architecture": architecture, "builder_version": 2,
              "launcher_digest": hashlib.sha256(launcher).hexdigest(), "interface": INTERFACE}
    identity = hashlib.sha256(canonical(recipe)).hexdigest()
    folder = state / "builds" / identity
    existing = folder / "build.json"
    if existing.is_file():
        metadata = read_json(existing)
        inspect_build(state, identity)
        return metadata
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "source.zip").write_bytes(bundle)
    try:
        with tempfile.TemporaryDirectory(prefix="catalyst-build-", dir=folder) as temporary:
            context = Path(temporary)
            extract_bundle(bundle, context)
            # Bundle identities contain bytes, not host permissions. Normalize
            # COPY inputs so a restrictive service umask cannot break non-root
            # container users or silently change a content-addressed build.
            for item in context.rglob("*"):
                item.chmod(0o755 if item.is_dir() else 0o644)
            source_tag = f"catalyst-source:{identity}"
            docker_output(["build", "--label", f"catalyst.source={snapshot['version']}",
                           "--tag", source_tag, "--file", str(context / execution["dockerfile"]),
                           str(context)], timeout=timeout)
            base_id = docker_output(["image", "inspect", source_tag, "--format", "{{.Id}}"])
            if not IMAGE_RE.fullmatch(base_id):
                raise CatalystError("Docker did not return an immutable image identity.")
            # BuildKit cannot resolve bare local image IDs in FROM. Use a content-named
            # local tag and verify it against the recorded ID before every evaluation.
            base_tag = f"catalyst-source-image:{base_id.removeprefix('sha256:')}"
            docker_output(["tag", base_id, base_tag])
            wrapper = context / ".catalyst-wrapper"
            wrapper.mkdir()
            (wrapper / "launch.py").write_bytes(launcher)
            write_json(wrapper / "execution.json", execution)
            (wrapper / "Dockerfile").write_text(
                f"FROM {base_tag}\nUSER root\n"
                "COPY launch.py execution.json /opt/catalyst/\n"
                "RUN command -v python3 && command -v bash\n"
                "ENTRYPOINT []\nCMD [\"/bin/bash\"]\n"
                "WORKDIR /workspace/repo\n"
            )
            for item in wrapper.iterdir():
                item.chmod(0o644)
            image_tag = f"catalyst-harness:{identity}"
            docker_output(["build", "--network", "none", "--label",
                           f"catalyst.source={snapshot['version']}", "--tag", image_tag,
                           str(wrapper)], timeout=timeout)
            image_id = docker_output(["image", "inspect", image_tag, "--format", "{{.Id}}"])
            if not IMAGE_RE.fullmatch(image_id):
                raise CatalystError("Docker did not return an immutable image identity.")
            artifact_tag = f"catalyst-image:{image_id.removeprefix('sha256:')}"
            docker_output(["tag", image_id, artifact_tag])
    except Exception:
        # An interrupted build has no successful build record and is safe to retry.
        raise
    metadata = {"schema_version": 1, "id": identity, **recipe, "image_id": image_id,
                "image_tag": image_tag, "artifact_tag": artifact_tag, "execution": execution,
                "harness": {key: snapshot[key] for key in ("id", "version")},
                "created_at": now(), "evidence": "local-build"}
    write_json(existing, metadata)
    return metadata


def inspect_build(state: Path, identity: str) -> dict:
    version_id(identity)
    file = state / "builds" / identity / "build.json"
    if not file.is_file():
        raise CatalystError("Build not found; run catalyst harness build PATH first.")
    metadata = read_json(file)
    image_id = metadata.get("image_id", "")
    if not isinstance(image_id, str) or not IMAGE_RE.fullmatch(image_id):
        raise CatalystError("Invalid built image identity.")
    inspected = json.loads(docker_output(["image", "inspect", image_id]))[0]
    if (inspected["Id"] != image_id
            or inspected.get("Config", {}).get("Labels", {}).get("catalyst.source")
            != metadata["source_digest"]):
        raise CatalystError("Built image does not match the recorded source.")
    tagged_id = docker_output(["image", "inspect", metadata["artifact_tag"], "--format", "{{.Id}}"])
    if tagged_id != image_id:
        raise CatalystError("Content-named image tag no longer identifies this build.")
    return metadata


def smoke(state: Path, identity: str, workspace: Path, *, problem=None, timeout=120) -> dict:
    """Run the complete entrypoint on a copy, without models or host credentials."""
    metadata = inspect_build(state, identity)
    workspace = workspace.resolve()
    if not workspace.is_dir():
        raise CatalystError("Smoke test requires an existing workspace directory.")
    if timeout < 1:
        raise CatalystError("Smoke timeout must be positive.")
    if problem:
        from .problems import validate_workspace
        validate_workspace(problem, workspace)
    attempt = "smoke-" + uuid.uuid4().hex[:16]
    folder = state / "smoke" / attempt
    folder.mkdir(parents=True)
    shutil.copytree(workspace, folder / "workspace",
                    ignore=shutil.ignore_patterns(".git", ".env*", ".catalyst", ".venv",
                                                 "__pycache__", ".DS_Store"),
                    symlinks=True)
    # Host symlinks must not be followed through the container bind.
    if any(item.is_symlink() for item in (folder / "workspace").rglob("*")):
        raise CatalystError("Smoke workspaces must not contain symlinks.")
    input_dir = folder / "input"
    input_dir.mkdir()
    problem_ref = ({"id": problem["id"], "version": hashlib.sha256(canonical(problem)).hexdigest()}
                   if problem else {"id": "smoke", "version": None})
    task = {"schema_version": 1, "problem": problem_ref,
            "workspace": "/workspace/repo",
            "candidate_paths": problem["candidate_paths"] if problem else [],
            "instruction": problem["title"] if problem else "",
            "gateway": None, "model": None, "evidence": "smoke"}
    write_json(input_dir / "task.json", task)
    container = "catalyst-" + attempt
    command = [
        "run", "--rm", "--name", container, "--network", "none", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--cpus", "2", "--memory", "2g",
        "--pids-limit", "256", "--mount",
        f"type=bind,source={folder / 'workspace'},target=/workspace/repo",
        "--mount", f"type=bind,source={input_dir},target=/opt/catalyst/input,readonly",
        "--entrypoint", "python3", metadata["image_id"],
        "/opt/catalyst/launch.py", "/opt/catalyst/input/task.json",
    ]
    result = {"id": attempt, "build_id": identity, "source_digest": metadata["source_digest"],
              "image_id": metadata["image_id"], "evidence": "smoke", "created_at": now()}
    try:
        result.update(status="completed", output=docker_output(command, timeout=timeout))
    except CatalystError as error:
        result.update(status="failed", error=str(error))
    finally:
        # A host timeout does not terminate a container by itself.
        subprocess.run(["docker", "rm", "-f", container], capture_output=True, timeout=30)
    write_json(folder / "result.json", result)
    return result


def model_profile(source: Path, requested: str, provider="openai") -> dict:
    """Resolve model identity from Dungeness's trusted accounting policy."""
    from .dungeness import yaml_file
    if not requested or not isinstance(requested, str):
        raise CatalystError("An executable evaluation requires an explicit --model.")
    prices = yaml_file(source / "services/gateway/pricing.yaml")
    matches = [entry for entry in prices.get("entries", [])
               if entry.get("provider") == provider
               and requested in entry.get("request_models", [])]
    if len(matches) != 1:
        raise CatalystError("Select a provider/model from the pinned Dungeness pricing policy.")
    return {"provider": provider, "upstream_id": matches[0]["upstream_id"],
            "request_model": requested, "api": "openai-responses" if provider == "openai-chatgpt" else "openai-completions",
            "name_format": "request", **({"context_window": 1050000,
            "supported_reasoning_efforts": ["low", "medium", "high", "xhigh", "max"]}
            if provider == "openai-chatgpt" else {})}


def install_agent(runtime: Path, build_record: dict, model: dict, task_input: dict) -> tuple[str, list[str]]:
    """Install one trusted adapter in the disposable Dungeness checkout."""
    token = "executable-" + build_record["id"]
    namespace = "projects/catalyst"
    agent_dir = runtime / "agents" / namespace / token
    agent_dir.mkdir(parents=True)
    from .dungeness import write_yaml
    subscription = model["provider"] == "openai-chatgpt"
    write_yaml(agent_dir / "agent.yaml", {
        "schema_version": 1, "type": "agent", "namespace": namespace, "id": token,
        "execution_mode": "installed",
        "package": {"name": INTERFACE, "version": build_record["source_digest"]},
        "model": model,
        "environment": {} if subscription else {"OPENAI_API_KEY": "testbed"},
        **({"authentication": {"mode": "chatgpt-subscription", "credential": "codex", "isolation": "reduced"}} if subscription else {}),
        "harbor": {"agent": "codex" if subscription else "catalyst-executable", "import_path": "catalyst_executable:CatalystExecutable",
                   "kwargs": {"task_input": task_input, **({"web_search": "disabled"} if subscription else {})}},
    })
    # Source was built once. Dungeness adds only its pinned task workspace and clients.
    (agent_dir / "Dockerfile").write_text(
        f"FROM {build_record['artifact_tag']}\nUSER root\n"
        # Dungeness requires this marker for Codex runtime images. The actual
        # executable and its version are already bound by the built source.
        + ("ARG CODEX_VERSION=source\n" if subscription else "")
        +
        "COPY workspace/ /workspace/repo/\n"
        "COPY web_client.py /usr/local/bin/web\n"
        "COPY evaluate.py /usr/local/bin/evaluate\n"
        "COPY run_status.py /usr/local/bin/run-status\n"
        "COPY candidate_state.py /usr/local/bin/candidate-state\n"
        "COPY knowledge_base.py /usr/local/bin/knowledge-base\n"
        "RUN chmod 0555 /usr/local/bin/web /usr/local/bin/evaluate "
        "/usr/local/bin/run-status /usr/local/bin/candidate-state /usr/local/bin/knowledge-base\n"
        "WORKDIR /workspace/repo\n"
    )
    adapter = runtime / "adapters" / "harbor" / "catalyst_executable.py"
    adapter.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(RUNTIME / "harbor_agent.py", adapter)
    return f"agent:{namespace}/{token}", [str(agent_dir.relative_to(runtime)),
                                         str(adapter.relative_to(runtime))]
