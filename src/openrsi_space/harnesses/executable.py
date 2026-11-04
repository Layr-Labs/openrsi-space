"""Executable source packages and local Docker builds.

The same functions can run on a dedicated worker. Local builds are not official
evidence, and this module does not accept provider credentials.
"""
from __future__ import annotations
from openrsi_space.compatibility import image_source, image_runtime_root, LEGACY_STATE, PROBLEM_PREFIX

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import uuid

from openrsi_space.common import (
    OpenRSIError, canonical, extract_bundle, now, read_json, safe_relative,
    snapshot_directory, version_id, write_json,
)

from openrsi_space.contracts.harness import INTERFACE, IMAGE_RE, SOURCE_EXCLUDES, validate_execution

RUNTIME = Path(__file__).resolve().parents[1] / "runtime"

def create_starter(target: Path) -> dict:
    """Add editable source; problem toolchains belong in the solver's Dockerfile."""
    (target / "README.md").write_text(
        "# Harness setup\n\n"
        "Replace agent.py with your autonomous solver. This starter makes no model calls.\n\n"
        "Before selecting a framework, pair its API format and adapter with your\n"
        "provider, exact model and credential method. Provider/model flags do not\n"
        "translate API requests. Check helper calls such as titles and compaction,\n"
        "function tools, tool results, streaming and usage reporting against a strict mock.\n"
        "Use only the gateway endpoints assigned in OPENRSI_TASK; keep credentials\n"
        "outside the harness. A packaging smoke check does not establish live compatibility.\n\n"
        "Read https://github.com/Layr-Labs/openrsi-space/blob/main/docs/harness-compatibility.md\n"
        "and report checks completed or skipped before an authorized model-consuming run.\n"
    )
    (target / "Dockerfile").write_text(
        "FROM python:3.12-slim-bookworm\n"
        "COPY . /opt/harness/\n"
        "WORKDIR /workspace/repo\n"
    )
    (target / "agent.py").write_text(
        '"""Replace this baseline with your autonomous solver. No model calls yet."""\n'
        "import json\n"
        "import os\n"
        "from pathlib import Path\n\n"
        'task = json.loads(Path(os.environ["OPENRSI_TASK"]).read_text())\n'
        'workspace = Path(task["workspace"])\n'
        'assert workspace.is_dir()\n'
        'print(json.dumps({"status": "completed", "problem": task["problem"],\n'
        '                  "candidate_paths": task["candidate_paths"]}))\n'
    )
    return {"interface": INTERFACE, "dockerfile": "Dockerfile",
            "entrypoint": ["python3", "/opt/harness/agent.py"]}


def docker_output(argv: list[str], *, timeout=120) -> str:
    from openrsi_space.job_control import check_cancelled
    from openrsi_space.job_control import signal_group
    import signal
    check_cancelled()
    try:
        process = subprocess.Popen(["docker", *argv], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, start_new_session=True)
        deadline = time.monotonic() + timeout
        try:
            while True:
                check_cancelled()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(process.args, timeout)
                try:
                    stdout, stderr = process.communicate(timeout=min(.25, remaining))
                    break
                except subprocess.TimeoutExpired:
                    if time.monotonic() >= deadline:
                        raise
            check_cancelled()
        except BaseException:
            signal_group(process.pid, signal.SIGINT)
            try:
                process.communicate(timeout=20)
            except subprocess.TimeoutExpired:
                signal_group(process.pid, signal.SIGKILL)
                process.communicate()
            raise
    except (OSError, subprocess.TimeoutExpired) as error:
        raise OpenRSIError(f"Docker command could not complete: {error}") from error
    if process.returncode:
        raise OpenRSIError(stderr[-4000:] or stdout[-4000:])
    return stdout.strip()


def build(state: Path, harness_path: Path, *, timeout=1200) -> dict:
    snapshot, bundle = snapshot_directory(harness_path, exclude=SOURCE_EXCLUDES)
    if snapshot["kind"] != "harness":
        raise OpenRSIError("Build requires a harness package.")
    execution = snapshot["document"].get("execution")
    validate_execution(execution)
    if execution["dockerfile"] not in snapshot["files"]:
        raise OpenRSIError("The build recipe is missing from the source package.")
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
        with tempfile.TemporaryDirectory(prefix="openrsi-build-", dir=folder) as temporary:
            context = Path(temporary)
            extract_bundle(bundle, context)
            # Bundle identities contain bytes, not host permissions. Normalize
            # COPY inputs so a restrictive service umask cannot break non-root
            # container users or silently change a content-addressed build.
            for item in context.rglob("*"):
                item.chmod(0o755 if item.is_dir() else 0o644)
            source_tag = f"openrsi-source:{identity}"
            docker_output(["build", "--label", f"openrsi.source={snapshot['version']}",
                           "--tag", source_tag, "--file", str(context / execution["dockerfile"]),
                           str(context)], timeout=timeout)
            base_id = docker_output(["image", "inspect", source_tag, "--format", "{{.Id}}"])
            if not IMAGE_RE.fullmatch(base_id):
                raise OpenRSIError("Docker did not return an immutable image identity.")
            # BuildKit cannot resolve bare local image IDs in FROM. Use a content-named
            # local tag and verify it against the recorded ID before every evaluation.
            base_tag = f"openrsi-source-image:{base_id.removeprefix('sha256:')}"
            docker_output(["tag", base_id, base_tag])
            wrapper = context / ".openrsi-wrapper"
            wrapper.mkdir()
            (wrapper / "launch.py").write_bytes(launcher)
            write_json(wrapper / "execution.json", execution)
            (wrapper / "Dockerfile").write_text(
                f"FROM {base_tag}\nUSER root\n"
                "COPY launch.py execution.json /opt/openrsi/\n"
                "RUN command -v python3 && command -v bash\n"
                "ENTRYPOINT []\nCMD [\"/bin/bash\"]\n"
                "WORKDIR /workspace/repo\n"
            )
            for item in wrapper.iterdir():
                item.chmod(0o644)
            image_tag = f"openrsi-harness:{identity}"
            docker_output(["build", "--network", "none", "--label",
                           f"openrsi.source={snapshot['version']}", "--tag", image_tag,
                           str(wrapper)], timeout=timeout)
            image_id = docker_output(["image", "inspect", image_tag, "--format", "{{.Id}}"])
            if not IMAGE_RE.fullmatch(image_id):
                raise OpenRSIError("Docker did not return an immutable image identity.")
            artifact_tag = f"openrsi-image:{image_id.removeprefix('sha256:')}"
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
        raise OpenRSIError("Build not found; run openrsi-space harness build PATH first.")
    metadata = read_json(file)
    image_id = metadata.get("image_id", "")
    if not isinstance(image_id, str) or not IMAGE_RE.fullmatch(image_id):
        raise OpenRSIError("Invalid built image identity.")
    inspected = json.loads(docker_output(["image", "inspect", image_id]))[0]
    if (inspected["Id"] != image_id
            or image_source(inspected.get("Config", {}).get("Labels", {}))
            != metadata["source_digest"]):
        raise OpenRSIError("Built image does not match the recorded source.")
    tagged_id = docker_output(["image", "inspect", metadata["artifact_tag"], "--format", "{{.Id}}"])
    if tagged_id != image_id:
        raise OpenRSIError("Content-named image tag no longer identifies this build.")
    return metadata


def smoke(state: Path, identity: str, workspace: Path, *, problem=None, timeout=120) -> dict:
    """Run the complete entrypoint on a copy, without models or host credentials."""
    metadata = inspect_build(state, identity)
    workspace = workspace.resolve()
    if not workspace.is_dir():
        raise OpenRSIError("Smoke test requires an existing workspace directory.")
    if timeout < 1:
        raise OpenRSIError("Smoke timeout must be positive.")
    if problem:
        from openrsi_space.challenge.catalog import validate_workspace
        validate_workspace(problem, workspace)
    attempt = "smoke-" + uuid.uuid4().hex[:16]
    folder = state / "smoke" / attempt
    folder.mkdir(parents=True)
    shutil.copytree(workspace, folder / "workspace",
                    ignore=shutil.ignore_patterns(".git", ".env*", ".openrsi", LEGACY_STATE, ".venv",
                                                 "__pycache__", ".DS_Store"),
                    symlinks=True)
    # Host symlinks must not be followed through the container bind.
    if any(item.is_symlink() for item in (folder / "workspace").rglob("*")):
        raise OpenRSIError("Smoke workspaces must not contain symlinks.")
    protected = []
    if problem and problem.get('dungeness', {}).get('scaffold'):
        from openrsi_space.challenge.assets import asset_path
        from openrsi_space.challenge.preparation import yaml_file
        manifest = asset_path(folder, problem['dungeness']['scaffold'])
        for source, target in yaml_file(manifest).get('trusted_files', {}).items():
            safe_relative(source)
            safe_relative(target)
            original = manifest.parent / source
            if original.is_symlink() or not original.resolve().is_relative_to(manifest.parent.resolve()):
                raise OpenRSIError('Trusted scaffold file escapes its manifest.')
            copied = folder / 'workspace' / target
            copied.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, copied)
            copied.chmod(0o444)
            protected.append((copied, target))
    input_dir = folder / "input"
    input_dir.mkdir()
    problem_ref = ({"id": problem["id"], "version": hashlib.sha256(canonical(problem)).hexdigest()}
                   if problem else {"id": "smoke", "version": None})
    task = {"schema_version": 1, "problem": problem_ref,
            "workspace": "/workspace/repo",
            "candidate_paths": problem["candidate_paths"] if problem else [],
            "instruction": problem["title"] if problem else "",
            "gateway": None, "model": None, "evidence": "smoke",
            "remaining_seconds": timeout, "readonly_workspace_paths": [target for _, target in protected]}
    write_json(input_dir / "task.json", task)
    container = "openrsi-" + attempt
    runtime_root = image_runtime_root(metadata)
    command = [
        "run", "--rm", "--name", container, "--network", "none", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--cpus", "2", "--memory", "2g",
        "--pids-limit", "256", "--mount",
        f"type=bind,source={folder / 'workspace'},target=/workspace/repo",
        "--mount", f"type=bind,source={input_dir},target={runtime_root}/input,readonly",
        *[arg for copied, target in protected for arg in
          ('--mount', f'type=bind,source={copied},target=/workspace/repo/{target},readonly')],
        "--entrypoint", "python3", metadata["image_id"],
        f"{runtime_root}/launch.py", f"{runtime_root}/input/task.json",
    ]
    result = {"id": attempt, "build_id": identity, "source_digest": metadata["source_digest"],
              "image_id": metadata["image_id"], "evidence": "smoke", "created_at": now()}
    try:
        result.update(status="completed", output=docker_output(command, timeout=timeout))
    except OpenRSIError as error:
        result.update(status="failed", error=str(error))
    finally:
        # A host timeout does not terminate a container by itself.
        subprocess.run(["docker", "rm", "-f", container], capture_output=True, timeout=30)
    write_json(folder / "result.json", result)
    return result
