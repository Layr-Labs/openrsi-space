"""Small generated source fixture; no shipped solver or model calls."""
from pathlib import Path

from openrsi_space.common import write_json
from openrsi_space.executable import create_starter


def evaluation():
    return {"schema_version": 3, "llm_access": {"grant_id": "grant_contract_test"},
            "model": {"provider": "openai", "name": "gpt-5.6-sol"},
            "max_model_credits": 20,
            "limits": {"max_model_tokens": 100000, "max_seconds": 900}}


def create_harness(target: Path):
    target.mkdir(parents=True)
    write_json(target / "harness.json", {
        "schema_version": 1, "kind": "harness", "id": "test-agent", "title": "Test agent",
        "execution": create_starter(target),
    })
    write_json(target / "evaluation.json", evaluation())
