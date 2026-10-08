"""A file/CLI adapter. No Dungeness implementation is imported or vendored."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import uuid

import yaml

from .common import (
    CatalystError, canonical, extract_bundle, finite_number, identifier, now,
    read_json, safe_relative, snapshot_directory, write_json,
)


def git(root: Path, *args) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if result.returncode:
        raise CatalystError(result.stderr.strip() or "Git command failed.")
    return result.stdout.strip()


def configure(state: Path, source: Path) -> dict:
    source = source.expanduser().resolve()
    if not (source / "dungeness").is_file():
        raise CatalystError(f"Dungeness CLI not found in {source}")
    if git(source, "status", "--porcelain"):
        raise CatalystError("Pin a clean Dungeness checkout so the execution code is reproducible.")
    config = {"schema_version": 1, "dungeness": {"path": str(source), "commit": git(source, "rev-parse", "HEAD")}}
    write_json(state / "config.json", config)
    return config


def installation(state: Path) -> dict:
    config_path = state / "config.json"
    if not config_path.is_file():
        raise CatalystError("Run catalyst init --dungeness PATH first.")
    config = read_json(config_path)["dungeness"]
    source = Path(config["path"])
    if git(source, "rev-parse", "HEAD") != config["commit"]:
        raise CatalystError("Dungeness HEAD differs from the pin. Run catalyst init to deliberately update it.")
    if git(source, "status", "--porcelain"):
        raise CatalystError("Dungeness checkout has uncommitted changes.")
    return config


def yaml_file(path: Path) -> dict:
    document = yaml.safe_load(path.read_text())
    if not isinstance(document, dict):
        raise CatalystError(f"Expected a mapping: {path}")
    return document


def find_manifest(root: Path, kind: str, reference: str) -> Path:
    if not isinstance(reference, str) or not reference.startswith(kind + ":"):
        raise CatalystError(f"Use a fully qualified {kind} reference.")
    namespace, _, local_id = reference[len(kind) + 1:].rpartition("/")
    if not namespace or not local_id:
        raise CatalystError(f"Invalid {kind} reference.")
    # Match manifest identities rather than allowing a reference to become a path.
    matches = []
    pattern = "*.yaml" if kind == "checkpoint" else f"{kind}.yaml"
    for path in (root / (kind + "s")).rglob(pattern):
        doc = yaml_file(path)
        if doc.get("namespace") == namespace and doc.get("id") == local_id:
            matches.append(path)
    if len(matches) != 1:
        raise CatalystError(f"Expected one installed manifest for {reference}; found {len(matches)}.")
    return matches[0]


def native_problem(source: Path, reference: str, checkpoint: str) -> tuple[dict, dict, str]:
    task_path = find_manifest(source, "task", reference)
    task = yaml_file(task_path)
    problem = task["relations"]["problem"]
    semantic = find_manifest(source, "problem", problem)
    metric = yaml_file(semantic)["data"]["metric"]
    instruction = (task_path.parent / safe_relative(task["instruction"])).read_text()
    return {"task": reference, "checkpoint": checkpoint}, metric, instruction


def write_yaml(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, sort_keys=False))


def prepare(state: Path, problem_path: Path, harness_path: Path, budget: float,
            max_tokens: int, resume: str | None = None, env_file: str | None = None, *,
            build_id: str | None = None, model: str | None = None, provider="openai", reasoning_effort=None) -> dict:
    finite_number(budget, nonnegative=True)
    if budget <= 0 or max_tokens < 1:
        raise CatalystError("Evaluation requires a positive budget and token cap.")
    config = installation(state)
    source = Path(config["path"])
    problem, problem_zip = snapshot_directory(problem_path)
    from .executable import SOURCE_EXCLUDES
    harness, harness_zip = snapshot_directory(harness_path, exclude=SOURCE_EXCLUDES)
    if problem["kind"] != "problem" or harness["kind"] != "harness":
        raise CatalystError("Evaluation needs a problem package and a harness package.")
    p, h = problem["document"], harness["document"]
    build_record = None
    executable_model = None
    if "execution" in h:
        from .executable import inspect_build, model_profile
        if not build_id or not model:
            raise CatalystError("Executable evaluations require --build BUILD_ID and --model MODEL.")
        build_record = inspect_build(state, build_id)
        if build_record["source_digest"] != harness["version"]:
            raise CatalystError("Harness source changed since this build. Build the current source first.")
        executable_model = model_profile(source, model, provider)
        if reasoning_effort:
            executable_model["defaults"] = {"reasoning_effort": reasoning_effort}
    else:
        if build_id or model:
            raise CatalystError("--build and --model apply only to executable harnesses.")
        find_manifest(source, "agent", h["agent"])
    execution = p.get("execution", {})
    native = "task" in execution
    if native:
        original_task = yaml_file(find_manifest(source, "task", execution["task"]))
        checkpoint = execution.get("checkpoint", "")
        if not checkpoint.startswith("checkpoint:"):
            raise CatalystError("A native task requires a checkpoint reference.")
        checkpoint_document = yaml_file(find_manifest(source, "checkpoint", checkpoint))
        interface = checkpoint_document["data"]["interface"]
        paths = original_task["interfaces"][interface]["candidate"]["allowed_paths"]
    else:
        repository = execution.get("repository", {})
        if not str(repository.get("url", "")).startswith("https://"):
            raise CatalystError("Dungeness requires an HTTPS source repository. Edit problem.json execution.repository.")
        commit = repository.get("commit", "")
        import re
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise CatalystError("Set execution.repository.commit to the full committed source SHA.")
        paths = execution.get("candidate_paths", [])
        if not paths:
            raise CatalystError("Declare at least one candidate path.")
        for path in paths:
            safe_relative(path)
        for filename in ("Dockerfile", "grade.py", "test.sh"):
            if not (problem_path / "verifier" / filename).is_file():
                raise CatalystError(f"Missing verifier/{filename}.")

    run_id = "eval-" + uuid.uuid4().hex[:16]
    folder = state / "evaluations" / run_id
    folder.mkdir(parents=True)
    for kind, snapshot, content in (("problem", problem, problem_zip), ("harness", harness, harness_zip)):
        (folder / f"{kind}.zip").write_bytes(content)
        extract_bundle(content, folder / "inputs" / kind)
    problem_path = folder / "inputs" / "problem"
    harness_path = folder / "inputs" / "harness"
    runtime = folder / "dungeness"
    result = subprocess.run(["git", "clone", "--quiet", "--shared", "--no-checkout", str(source), str(runtime)],
                            capture_output=True, text=True)
    if result.returncode:
        raise CatalystError(result.stderr)
    git(runtime, "checkout", "--quiet", "--detach", config["commit"])
    agent_ref = h.get("agent")
    added_agent_paths = []
    if build_record:
        from .executable import install_agent
        task_input = {
            "schema_version": 1, "problem": {k: problem[k] for k in ("id", "version")},
            "harness": {k: harness[k] for k in ("id", "version")},
            "candidate_paths": paths, "budget": {"max_usd": budget, "max_model_tokens": max_tokens},
            "evidence": "local-evaluation",
            "model_provider": provider, "reasoning_effort": reasoning_effort,
        }
        agent_ref, added_agent_paths = install_agent(runtime, build_record, executable_model, task_input)
        if provider == "openai-chatgpt":
            launcher = runtime / "dungeness"
            original = launcher.read_text()
            before = 'tempfile.mkdtemp(prefix="dungeness-codex-auth-", dir="/tmp")'
            if original.count(before) != 1:
                raise CatalystError("Pinned Dungeness credential staging has changed.")
            launcher.write_text(original.replace(before, before.replace("/tmp", "/dev/shm")))
            added_agent_paths.append("dungeness")
    token = "catalyst-" + problem["version"]
    namespace = "projects/catalyst"
    task_path = runtime / "tasks" / namespace / token / "task.yaml"
    if native:
        task = original_task
    else:
        interface = execution.get("interface", "catalyst-file-v1")
        task = {
            "schema_version": 1, "type": "task", "namespace": namespace, "id": token,
            "instruction": "statement.md", "workspace": {"include": ["."]},
            "interfaces": {interface: {"candidate": {"allowed_paths": paths}, "verifier": token}},
            "resources": {"agent": {"timeout_sec": execution.get("timeout_sec", 900)}},
        }
        checkpoint_ns = namespace + "/" + token
        checkpoint = f"checkpoint:{checkpoint_ns}/{commit}"
        write_yaml(runtime / "checkpoints" / token / f"{commit}.yaml", {
            "schema_version": 1, "type": "checkpoint", "namespace": checkpoint_ns, "id": commit,
            "data": {"repository": repository, "interface": interface,
                     "web_cutoff": execution.get("web_cutoff", "1970-01-01T00:00:00.000Z"),
                     "history": {"anchor": commit, "distance_from_anchor": 0,
                                 "counting_method": "git-rev-list-ancestry-path-count"}},
        })
        verifier = runtime / "verifiers" / token
        shutil.copytree(problem_path / "verifier", verifier)
        write_yaml(verifier / "evaluator.lock.yaml", {
            "repository": execution.get("verifier_repository", repository),
            "include_paths": execution.get("verifier_include", ["check.py"]),
        })
    task.update({"schema_version": 1, "type": "task", "namespace": namespace, "id": token,
                 "instruction": "statement.md", "relations": {"problem": f"problem:{namespace}/{token}"}})
    write_yaml(task_path, task)
    write_yaml(runtime / "problems" / token / "problem.yaml", {
        "schema_version": 1, "type": "problem", "namespace": namespace, "id": token,
        "data": {"objective": p.get("description", p["title"]), "metric": p["metric"]},
    })
    instruction = (problem_path / "instructions.md").read_text()
    strategy = (harness_path / "instructions.md").read_text()
    (task_path.parent / "statement.md").write_text(instruction + "\n\n## Harness method\n\n" + strategy)

    kb_id = "catalyst-" + harness["version"]
    kb_path = runtime / "knowledge-bases" / namespace / kb_id
    knowledge = harness_path / "knowledge"
    kb_path.mkdir(parents=True)
    files = [f for f in sorted(knowledge.rglob("*")) if f.is_file()] if knowledge.is_dir() else []
    for file in files:
        target = kb_path / "notes" / file.relative_to(knowledge)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(file, target)
    (kb_path / "index.md").write_text("# Harness knowledge\n\n" + "\n".join(
        "- " + ("notes/" + f.relative_to(knowledge).as_posix()) for f in files) + "\n")
    write_yaml(kb_path / "knowledge-base.yaml", {
        "schema_version": 1, "type": "knowledge-base", "namespace": namespace, "id": kb_id,
        "title": h["title"], "entrypoint": "index.md",
        "interface": {"mode": "curated-corpus", "operations": ["status", "list", "search", "read"]},
        "preload": {"status": "ready", "intended_destination": "harness-knowledge",
                    "copy_contents": True, "core_files": ["index.md"]},
        "content_layers": {"knowledge": ["notes"] if files else ["index.md"]},
    })
    initialization = {"mode": "checkpoint", "knowledge_base": {
        "ref": f"knowledge-base:{namespace}/{kb_id}", "access": "sidecar"}}
    parent = None
    if resume:
        identifier(resume)
        parent_path = state / "evaluations" / resume / "evaluation.json"
        if not parent_path.is_file():
            raise CatalystError("Continuation needs a Catalyst evaluation with retained Dungeness outputs.")
        parent = read_json(parent_path)
        parent_record = Path(parent["record_path"])
        if not parent_record.is_file():
            raise CatalystError("The parent evaluation has no canonical run record yet.")
        parent_doc = read_json(parent_record)
        prior = runtime / "runs" / parent_doc["namespace"] / parent_doc["id"]
        prior.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(parent_record.parent, prior)
        initialization["resume_from"] = parent_doc["id"]

    environment_file = str(Path(env_file).expanduser().resolve()) if env_file else str(source / ".env")
    spec = {
        "schema_version": 1, "type": "run-spec", "namespace": namespace, "id": run_id,
        "task": f"task:{namespace}/{token}", "agent": agent_ref, "checkpoint": checkpoint,
        "budget": {"max_usd": budget, "max_model_tokens": max_tokens},
        "initialization": initialization,
        "web_search": {"profile": "web-search-profile:system/dungeness/disabled-v1"},
        "labels": {"catalyst_problem_version": problem["version"], "catalyst_harness_version": harness["version"]},
        "runtime": {"env_file": environment_file},
    }
    if h.get("agent_options"):
        spec["agent_options"] = h["agent_options"]
    spec_path = runtime / "run-specs" / namespace / f"{run_id}.yaml"
    write_yaml(spec_path, spec)
    # The upstream remains pinned. Generated research inputs get their own commit.
    git(runtime, "add", str(task_path.parent.relative_to(runtime)), "problems/" + token,
        "knowledge-bases/" + namespace + "/" + kb_id, str(spec_path.relative_to(runtime)),
        *added_agent_paths,
        *(["checkpoints/" + token, "verifiers/" + token] if not native else []))
    git(runtime, "-c", "user.name=Catalyst", "-c", "user.email=catalyst@localhost", "-c", "commit.gpgsign=false",
        "commit", "--quiet", "-m", f"Evaluation inputs {run_id}")
    record = runtime / "runs" / namespace / run_id / "record.json"
    metadata = {
        "id": run_id, "created_at": now(), "status": "prepared",
        "problem": {k: problem[k] for k in ("id", "version")},
        "harness": {k: harness[k] for k in ("id", "version")},
        "dungeness_commit": config["commit"], "execution_commit": git(runtime, "rev-parse", "HEAD"),
        "runtime": str(runtime), "spec_path": str(spec_path), "record_path": str(record),
        "parent": parent["id"] if parent else None, "budget": budget,
        "command": [str(runtime / "dungeness"), "run", str(spec_path),
                    "--namespace", namespace, "--run-id", run_id],
    }
    if build_record:
        metadata["build"] = {"id": build_record["id"], "source_digest": build_record["source_digest"],
                             "image_id": build_record["image_id"]}
    write_json(folder / "evaluation.json", metadata)
    return metadata


def execute(state: Path, identity: str) -> int:
    identifier(identity)
    metadata_path = state / "evaluations" / identity / "evaluation.json"
    metadata = read_json(metadata_path)
    if metadata["status"] != "prepared":
        raise CatalystError("This evaluation has already started. Create a new attempt to run again.")
    if metadata.get("build"):
        from .executable import inspect_build
        built = inspect_build(state, metadata["build"]["id"])
        if built["image_id"] != metadata["build"]["image_id"]:
            raise CatalystError("Prepared evaluation's built image changed.")
    metadata["status"] = "running"
    write_json(metadata_path, metadata)
    try:
        result = subprocess.run(metadata["command"], cwd=metadata["runtime"])
        metadata["status"] = "finished" if result.returncode == 0 else "failed"
        metadata["exit_code"] = result.returncode
        return result.returncode
    except (OSError, KeyboardInterrupt):
        metadata["status"] = "interrupted"
        raise
    finally:
        metadata["finished_at"] = now()
        write_json(metadata_path, metadata)


def normalize_run(record_path: Path, problem: dict, harness: dict, *,
                  identity: str | None = None, starting_cost: float | None = 0,
                  upstream_commit: str | None = None, association="user-associated") -> dict:
    raw = read_json(record_path)
    data = raw.get("data", {})
    if raw.get("type") != "run" or not isinstance(data, dict):
        raise CatalystError("Expected a canonical Dungeness run record.")
    if data.get("metric") != problem["document"]["metric"]:
        raise CatalystError("Dungeness metric differs from the selected problem.")
    model = data.get("model", {})
    model_name = model.get("upstream_id") or model.get("request_model") or "unknown"
    if not isinstance(model_name, str):
        raise CatalystError("Invalid model name in Dungeness record.")
    config = data.get("configuration", {})
    resolved = config.get("resolved", {})
    policies = resolved.get("policies", {})
    budget_policy = policies.get("budget", {})
    condition = {
        "provider": model.get("provider"), "model_options": model.get("options", {}),
        "policies": {k: v for k, v in policies.items() if k != "budget"},
        "evaluation": resolved.get("evaluation", {}),
        "evaluation_budget": budget_policy.get("evaluation", {}),
        "web_budget": budget_policy.get("web", {}),
        "web_search": resolved.get("web_search", {}),
        "resources": resolved.get("resources", {}),
        "checkpoint": data.get("checkpoint", {}).get("repository", {}),
        "web_cutoff": data.get("checkpoint", {}).get("web_cutoff"),
        "initialization": data.get("initialization", {}).get("mode", "checkpoint"),
        "continuation": bool(raw.get("relations", {}).get("resumed_from")),
        "dungeness_commit": upstream_commit or config.get("repository", {}).get("commit"),
    }
    # Model spend caps are viewing parameters. Verification and access policies
    # remain comparison conditions; knowledge contents belong to the harness.
    conditions = hashlib.sha256(canonical(condition)).hexdigest()
    cost_known = starting_cost is not None
    if starting_cost is not None:
        finite_number(starting_cost, nonnegative=True)
    offset = starting_cost or 0
    usage = data.get("usage", {})
    own_cost = usage.get("normalized_usd")
    if own_cost is not None:
        own_cost = finite_number(own_cost, nonnegative=True)
    observations = []
    warnings = []
    events = record_path.parent / "usage" / "events.jsonl"
    if events.is_file():
        for index, line in enumerate(events.read_text().splitlines(), 1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                warnings.append(f"Unreadable event at line {index}.")
                continue
            if event.get("kind") != "evaluation.completed" or event.get("source") != "evaluator":
                continue
            event_data = event.get("data", {})
            if event_data.get("status") not in {"ok", "valid", "success"}:
                continue
            try:
                score = finite_number(event_data.get("score"))
                cost = finite_number(event.get("usage", {}).get("normalized_usd"), nonnegative=True)
            except CatalystError:
                warnings.append(f"Evaluation at line {index} has no usable score/cost pair.")
                continue
            observations.append({"cost": offset + cost, "score": score,
                                 "kind": "evaluation", "at": event.get("observed_at")})
    # Clean-verifier outputs are observations of this run, not platform reproduction.
    # Harbor nests each trial under the job's run ID.
    finals = list((record_path.parent / "harbor").glob("*/*/verifier/score.json"))
    if len(finals) == 1 and own_cost is not None and data.get("status") == "completed":
        final = read_json(finals[0])
        valid = final.get("status") in {"ok", "valid", "success"} or final.get("valid") is True
        if valid and final.get("metric", problem["document"]["metric"]["name"]) == problem["document"]["metric"]["name"]:
            observations.append({"cost": offset + own_cost, "score": finite_number(final["score"]),
                                 "kind": "clean-verifier", "at": data.get("finished_at")})
    # Summary metrics are already Dungeness observations, not an independent verification claim.
    metric_name = problem["document"]["metric"]["name"]
    final_score = data.get("metrics", {}).get(metric_name)
    if final_score is not None and own_cost is not None and not any(p["kind"] == "clean-verifier" for p in observations):
        observations.append({"cost": offset + own_cost, "score": finite_number(final_score),
                             "kind": "reported-summary", "at": data.get("finished_at")})
    observations.sort(key=lambda p: p["cost"])
    identity = identifier(identity or raw["id"])
    return {
        "schema_version": 1, "kind": "run", "id": identity, "title": f"{harness['document']['title']} / {problem['document']['title']}",
        "problem": {k: problem[k] for k in ("id", "version")},
        "harness": {k: harness[k] for k in ("id", "version")},
        "metric": problem["document"]["metric"], "model": model_name, "conditions": conditions,
        "condition_label": f"{model.get('provider', 'unknown')} · {'continued' if condition['continuation'] else 'fresh'} · no platform verification",
        "condition_details": condition, "evidence": "contributor-reported",
        "status": data.get("status", "unknown"), "observations": observations,
        "total_cost": offset + own_cost if cost_known and own_cost is not None else None,
        "own_cost": own_cost, "starting_cost": starting_cost, "cost_known": cost_known,
        "billed_usd": usage.get("billed_usd"), "cost_unit": "normalized_model_usd",
        "dungeness_commit": condition["dungeness_commit"], "input_provenance": association,
        "source_record_sha256": hashlib.sha256(record_path.read_bytes()).hexdigest(),
        "source_run": {k: raw.get(k) for k in ("id", "namespace", "relations")},
        "created_at": raw.get("created_at"), "warnings": warnings,
    }


def import_evaluation(state: Path, identity: str) -> Path:
    identifier(identity)
    folder = state / "evaluations" / identity
    meta = read_json(folder / "evaluation.json")
    from .common import open_bundle
    problem, _ = open_bundle((folder / "problem.zip").read_bytes())
    harness, _ = open_bundle((folder / "harness.zip").read_bytes())
    starting = 0
    if meta.get("parent"):
        parent_path = state / "runs" / meta["parent"] / "run.json"
        if not parent_path.is_file():
            import_evaluation(state, meta["parent"])
        starting = read_json(parent_path).get("total_cost")
    document = normalize_run(Path(meta["record_path"]), problem, harness, identity=identity,
                             starting_cost=starting, upstream_commit=meta["dungeness_commit"],
                             association="staged-input-snapshots")
    if meta.get("build"):
        document["build"] = meta["build"]
    target = state / "runs" / identity
    write_json(target / "run.json", document)
    (target / "dungeness-record.json").write_bytes(Path(meta["record_path"]).read_bytes())
    return target
