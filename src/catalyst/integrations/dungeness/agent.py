"""Public Dungeness command adapter and model selection for Catalyst harnesses."""
from pathlib import Path
from catalyst.common import CatalystError
from catalyst.harnesses.executable import INTERFACE

def model_profile(source: Path, requested: str, provider="openai", pricing=None) -> dict:
    """Resolve model identity from Dungeness's trusted accounting policy."""
    from catalyst.credentials import require_active_models
    require_active_models([{"provider": provider}])
    from .providers import require_model_providers
    require_model_providers(source, [{"provider": provider}])
    from catalyst.challenge.preparation import yaml_file
    if not requested or not isinstance(requested, str):
        raise CatalystError("An executable evaluation requires an explicit --model.")
    prices = yaml_file(source / "services/gateway/pricing.yaml") if pricing is None else pricing
    matches = [entry for entry in prices.get("entries", [])
               if entry.get("provider") == provider
               and requested in entry.get("request_models", [])]
    if len(matches) != 1:
        raise CatalystError("Select a provider/model from the pinned Dungeness pricing policy.")
    if any("cache_write_1h_per_mtok" in rates for rates in (matches[0], matches[0].get("long_context", {}))):
        from catalyst.runtime_contract import require_capabilities
        require_capabilities(source, "cache-duration-accounting-v1")
    return {"provider": provider, "upstream_id": matches[0]["upstream_id"],
            "request_model": requested, "api": ("anthropic-messages" if provider in {"anthropic", "claude-subscription"}
                else "openai-responses" if provider == "openai-chatgpt"
                else "openai-completions"),
            "name_format": "request"}

def install_agent(runtime: Path, build_record: dict, model: dict, task_input: dict) -> tuple[str, list[str]]:
    """Install one trusted adapter in the disposable Dungeness checkout."""
    token = "executable-" + build_record["id"]
    namespace = "projects/catalyst"
    agent_dir = runtime / "agents" / namespace / token
    agent_dir.mkdir(parents=True)
    from catalyst.challenge.preparation import write_yaml
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
    return f"agent:{namespace}/{token}", [str(agent_dir.relative_to(runtime))]
