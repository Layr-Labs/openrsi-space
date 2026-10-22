"""Validate evaluation settings independently of HTTP and execution."""
import re
from catalyst.common import CatalystError
from .accounting import credit_limit, evaluation_models, model_prices

def validate_evaluation_config(config: dict, *, check_pricing=True, pricing=None) -> dict:
    version = config.get("schema_version") if isinstance(config, dict) else None
    if (not isinstance(config, dict)
            or set(config) != {"schema_version", "llm_access", "model", "max_model_credits", "limits"} | ({"models"} if version == 4 else set())
            or type(version) is not int or version not in (3, 4)):
        raise CatalystError("evaluation.json requires v3, or v4 with an explicit models list.")
    access = config["llm_access"]
    if (not isinstance(access, dict) or set(access) != {"grant_id"}
            or not isinstance(access["grant_id"], str)
            or not re.fullmatch(r"grant_[A-Za-z0-9_-]{8,100}", access["grant_id"])):
        raise CatalystError("Set llm_access.grant_id to a private evaluator grant reference; never include a token.")
    models = evaluation_models(config)
    if not isinstance(models, list) or not 1 <= len(models) <= 16 or config["model"] != models[0]:
        raise CatalystError("models must contain 1..16 entries, starting with the default model.")
    seen = set()
    for model in models:
        validate_model(model, check_pricing=check_pricing, pricing=pricing)
        key = (model["provider"], model["name"])
        if key in seen:
            raise CatalystError("Duplicate allowed model.")
        seen.add(key)
    credit_limit(config["max_model_credits"])
    limits = config["limits"]
    validate_limits(limits)
    return config


def validate_limits(limits):
    if (not isinstance(limits, dict) or "max_seconds" not in limits
            or set(limits) - {"max_model_tokens", "max_seconds"}):
        raise CatalystError("limits requires max_seconds and accepts optional max_model_tokens.")
    seconds = limits["max_seconds"]
    if type(seconds) is not int or seconds <= 0:
        raise CatalystError("max_seconds must be a positive integer.")
    tokens = limits.get("max_model_tokens")
    if tokens is not None and (type(tokens) is not int or tokens <= 0):
        raise CatalystError("max_model_tokens must be null or a positive integer.")


def limits_within(requested, allowed):
    """An absent/null token cap is unlimited, never below a finite allowance."""
    try:
        validate_limits(requested)
        validate_limits(allowed)
    except CatalystError:
        return False
    if requested["max_seconds"] > allowed["max_seconds"]:
        return False
    ceiling = allowed.get("max_model_tokens")
    tokens = requested.get("max_model_tokens")
    return ceiling is None or (tokens is not None and tokens <= ceiling)


def validate_model(model, *, check_pricing=True, pricing=None):
    if (not isinstance(model, dict) or (not {"provider", "name"} <= set(model) or set(model) - {"provider", "name", "reasoning_effort"})
            or any(not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9._/:-]{1,120}", value)
                   for value in model.values())):
        raise CatalystError("model requires a provider and exact model name.")
    if "reasoning_effort" in model and model["reasoning_effort"] not in {"low", "medium", "high", "xhigh", "max"}:
        raise CatalystError("Unsupported reasoning effort.")
    from catalyst.credentials import PROVIDERS
    if model["provider"] not in PROVIDERS:
        raise CatalystError("Provider requires an authentication/protocol adapter.")
    from catalyst.provider_profiles import PROFILES, upstream_model
    if model['provider'] in PROFILES:
        try:
            upstream_model(model['provider'], model['name'])
        except ValueError as error:
            raise CatalystError(str(error)) from None
    if check_pricing:
        model_prices(model, pricing)
