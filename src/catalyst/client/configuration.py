"""Resolve solver settings from a local file and explicit overrides."""
import copy
from pathlib import Path
from catalyst.common import CatalystError, read_json
from catalyst.contracts.evaluation import validate_evaluation_config

def evaluation_config(path: Path, overrides: dict | None = None, *, check_pricing=True, pricing=None) -> dict:
    """Resolve run settings independently of the submitted source bundle."""
    overrides = overrides or {}
    allowed = {"provider", "model", "reasoning_effort", "budget", "max_tokens", "max_seconds"}
    if set(overrides) - allowed:
        raise CatalystError("Unknown evaluation setting.")
    if path.is_file():
        config = copy.deepcopy(read_json(path))
        if not isinstance(config, dict):
            raise CatalystError("evaluation.json must be an object.")
    else:
        if not {"provider", "model", "budget"} <= set(overrides):
            raise CatalystError("Supply evaluation.json or --provider, --model and --budget.")
        config = {
            "schema_version": 3,
            "llm_access": {"grant_id": "grant_temporary_provider"},
            "model": {},
            "max_model_credits": overrides["budget"],
            "limits": {"max_model_tokens": None, "max_seconds": 900},
        }
    if ("provider" in overrides) != ("model" in overrides):
        raise CatalystError("Set --provider and --model together.")
    if {"provider", "model", "reasoning_effort"} & set(overrides):
        if config.get("schema_version") == 4:
            raise CatalystError("For a model ensemble, edit models in evaluation.json instead of model flags.")
        if "provider" in overrides:
            # Never carry provider-specific reasoning settings to another model.
            config["model"] = {"provider": overrides["provider"], "name": overrides["model"]}
        if "reasoning_effort" in overrides:
            if not isinstance(config.get("model"), dict):
                raise CatalystError("model must be an object.")
            config["model"]["reasoning_effort"] = overrides["reasoning_effort"]
    if "budget" in overrides:
        config["max_model_credits"] = overrides["budget"]
    for option, key in (("max_tokens", "max_model_tokens"), ("max_seconds", "max_seconds")):
        if option in overrides:
            if not isinstance(config.get("limits"), dict):
                raise CatalystError("limits must be an object.")
            config["limits"][key] = overrides[option]
    return validate_evaluation_config(config, check_pricing=check_pricing, pricing=pricing)
