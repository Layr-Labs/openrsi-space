"""Public Dungeness command adapter and model selection for Catalyst harnesses."""
from pathlib import Path
from catalyst.common import CatalystError
from catalyst.executable import INTERFACE

def model_profile(source: Path, requested: str, provider="openai", pricing=None) -> dict:
    """Resolve model identity from Dungeness's trusted accounting policy."""
    from .provider_profiles import PROFILES, upstream_model
    if provider in PROFILES:
        if not (source / "services/gateway/provider_profiles.py").is_file():
            raise CatalystError("Update the pinned Dungeness runtime for configured provider support.")
        try:
            upstream_model(provider, requested)
        except ValueError as error:
            raise CatalystError(str(error)) from None
    from .task_setup import yaml_file
    if not requested or not isinstance(requested, str):
        raise CatalystError("An executable evaluation requires an explicit --model.")
    prices = yaml_file(source / "services/gateway/pricing.yaml") if pricing is None else pricing
    matches = [entry for entry in prices.get("entries", [])
               if entry.get("provider") == provider
               and requested in entry.get("request_models", [])]
    if len(matches) != 1:
        raise CatalystError("Select a provider/model from the pinned Dungeness pricing policy.")
    return {"provider": provider, "upstream_id": matches[0]["upstream_id"],
            "request_model": requested, "api": ("anthropic-messages" if provider == "anthropic"
                else "openai-responses" if provider in {"openai-chatgpt", "moonshot", "kimi-code"}
                else "openai-completions"),
            "name_format": "request", **({"context_window": 1050000,
            "supported_reasoning_efforts": ["low", "medium", "high", "xhigh", "max"]}
            if provider == "openai-chatgpt" else {})}

def install_agent(runtime: Path, build_record: dict, model: dict, task_input: dict) -> tuple[str, list[str]]:
    """Install one trusted adapter in the disposable Dungeness checkout."""
    from .provider_profiles import PROFILES, PROFILE_PATH
    registry = runtime / 'services/gateway/providers.json'
    if model['provider'] in PROFILES and not (runtime / 'services/gateway/provider_profiles.py').is_file():
        raise CatalystError('Update the pinned Dungeness runtime for configured provider support.')
    profile_paths = []
    if registry.is_file():
        registry.write_bytes(PROFILE_PATH.read_bytes())
        profile_paths.append(str(registry.relative_to(runtime)))
    token = "executable-" + build_record["id"]
    namespace = "projects/catalyst"
    agent_dir = runtime / "agents" / namespace / token
    agent_dir.mkdir(parents=True)
    from .task_setup import write_yaml
    write_yaml(agent_dir / "agent.yaml", {
        "schema_version": 1, "type": "agent", "namespace": namespace, "id": token,
        "execution_mode": "installed",
        "package": {"name": INTERFACE, "version": build_record["source_digest"]},
        "execution": {"interface": "dungeness-command-v1",
                      "entrypoint": ["python3", "/opt/catalyst/launch.py", "/tmp/dungeness-task.json"]},
        "task_input": {**task_input, "gateway_auth": "placeholder"},
    })
    # Source was built once. Dungeness adds only its pinned task workspace and clients.
    (agent_dir / "Dockerfile").write_text(
        f"FROM {build_record['artifact_tag']}\nUSER root\n"
        "COPY workspace/ /workspace/repo/\n"
        "COPY web_client.py /usr/local/bin/web\n"
        "COPY evaluate.py /usr/local/bin/evaluate\n"
        "COPY run_status.py /usr/local/bin/run-status\n"
        "COPY candidate_state.py /usr/local/bin/candidate-state\n"
        "RUN chmod 0555 /usr/local/bin/web /usr/local/bin/evaluate "
        "/usr/local/bin/run-status /usr/local/bin/candidate-state\n"
        "WORKDIR /workspace/repo\n"
    )
    return f"agent:{namespace}/{token}", [str(agent_dir.relative_to(runtime)), *profile_paths]

