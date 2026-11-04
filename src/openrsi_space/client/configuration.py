"""Resolve solver settings from a local file and explicit overrides."""
import copy
from pathlib import Path
from openrsi_space.common import OpenRSIError, read_json
from openrsi_space.contracts.evaluation import validate_evaluation_config

def evaluation_config(path: Path, overrides: dict | None = None, *, check_pricing=True, pricing=None) -> dict:
    """Resolve run settings independently of the submitted source bundle."""
    overrides = overrides or {}
    allowed = {"provider", "model", "reasoning_effort", "budget", "max_tokens", "max_seconds", "platform_funded"}
    if set(overrides) - allowed:
        raise OpenRSIError("Unknown evaluation setting.")
    if "platform_funded" in overrides and type(overrides["platform_funded"]) is not bool:
        raise OpenRSIError("platform_funded must be true or false.")
    if path.is_file():
        config = copy.deepcopy(read_json(path))
        if not isinstance(config, dict):
            raise OpenRSIError("evaluation.json must be an object.")
    else:
        if not {"provider", "model", "budget"} <= set(overrides):
            raise OpenRSIError("Supply evaluation.json or --provider, --model and --budget.")
        config = {
            "schema_version": 3,
            "llm_access": {"grant_id": "grant_temporary_provider"},
            "model": {},
            "max_model_credits": overrides["budget"],
            "limits": {"max_model_tokens": None, "max_seconds": 10800},
        }
    if ("provider" in overrides) != ("model" in overrides):
        raise OpenRSIError("Set --provider and --model together.")
    if {"provider", "model", "reasoning_effort"} & set(overrides):
        if config.get("schema_version") == 4:
            raise OpenRSIError("For a model ensemble, edit models in evaluation.json instead of model flags.")
        if "provider" in overrides:
            # Never carry provider-specific reasoning settings to another model.
            config["model"] = {"provider": overrides["provider"], "name": overrides["model"]}
        if "reasoning_effort" in overrides:
            if not isinstance(config.get("model"), dict):
                raise OpenRSIError("model must be an object.")
            config["model"]["reasoning_effort"] = overrides["reasoning_effort"]
    if overrides.get("platform_funded") is True:
        from openrsi_space.credentials import PLATFORM_GRANT
        config["llm_access"] = {"grant_id": PLATFORM_GRANT}
    if "budget" in overrides:
        config["max_model_credits"] = overrides["budget"]
    for option, key in (("max_tokens", "max_model_tokens"), ("max_seconds", "max_seconds")):
        if option in overrides:
            if not isinstance(config.get("limits"), dict):
                raise OpenRSIError("limits must be an object.")
            config["limits"][key] = overrides[option]
    return validate_evaluation_config(config, check_pricing=check_pricing, pricing=pricing)
