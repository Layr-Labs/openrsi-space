"""Temporary credential encoding for the HTTPS client; refresh tokens stay local."""
import base64
import json
from datetime import datetime, timezone
from pathlib import Path
from catalyst.common import CatalystError, canonical
from catalyst.protocol import APIError

TEMPORARY_GRANT = "grant_temporary_provider"
TOKEN_HEADER = "X-Catalyst-Model-Token"
MAX_TOKEN_BYTES = 8192
# Credential serialization/staging formats, not the service admission policy.
# Provider availability is discovered from the selected Dungeness runtime.
PROVIDER_ENV = {"openai": "TESTBED_OPENAI_API_KEY", "anthropic": "TESTBED_ANTHROPIC_API_KEY",
                "openrouter": "TESTBED_OPENROUTER_API_KEY"}
PROVIDERS = frozenset(PROVIDER_ENV) | {"openai-chatgpt", "claude-subscription"}
# Read historical configurations without re-enabling their credentials or execution.
RETIRED_PROVIDERS = frozenset({"kimi-code", "moonshot", "xai", "grok-subscription"})

def require_active_models(models):
    for model in models:
        if model["provider"] in RETIRED_PROVIDERS:
            raise CatalystError("This provider integration is retired; choose a provider supported by the selected Dungeness runtime.")

PREFIX = "chatgpt_"
ACCESS_PREFIX = "providers_"

def temporary_access(evaluation):
    return evaluation["llm_access"]["grant_id"] == TEMPORARY_GRANT

def validate_token(token):
    if (not isinstance(token, str) or not 8 <= len(token) <= MAX_TOKEN_BYTES
            or any(ord(character) < 33 or ord(character) > 126 for character in token)):
        raise APIError(400, "Supply a provider access token through the private token prompt.")

def validate_access(access):
    if (not isinstance(access, dict) or set(access) != {"access_token", "id_token", "account_id", "last_refresh"}
            or any(not isinstance(v, str) or not v or len(v) > 8192 for v in access.values())):
        raise CatalystError("A valid ChatGPT Codex login is required.")

def encode_codex_access(path):
    try:
        document = json.loads(Path(path).expanduser().read_text())
        if document.get("auth_mode") != "chatgpt":
            raise ValueError
        access = {name: document["tokens"].get(name) for name in ("access_token", "id_token", "account_id")}
        # Codex recognizes the login without this metadata but omits bearer
        # authentication on Responses requests. Preserve the native timestamp.
        access["last_refresh"] = document.get("last_refresh")
        validate_access(access)
        result = PREFIX + base64.urlsafe_b64encode(canonical(access)).decode()
        validate_token(result)
        return result
    except (OSError, ValueError, KeyError, TypeError):
        raise CatalystError("Cannot read a valid ChatGPT login from the selected Codex auth file.") from None

def decode_codex_access(value):
    try:
        if not isinstance(value, str) or not value.startswith(PREFIX):
            raise ValueError
        access = json.loads(base64.b64decode(value[len(PREFIX):], altchars=b"-_", validate=True))
        validate_access(access)
        return access
    except (ValueError, TypeError):
        raise CatalystError("Invalid temporary Codex access; submit using --codex-auth-file.") from None

def encode_provider_access(document):
    """Encode a private provider map for the existing HTTPS handoff channel."""
    validate_provider_access(document)
    encoded = ACCESS_PREFIX + base64.urlsafe_b64encode(canonical(document)).decode()
    validate_token(encoded)
    return encoded

def validate_session_access(value):
    # Exact fields deliberately exclude refresh tokens and entire login files.
    if not isinstance(value, dict) or set(value) != {"access_token", "expires_at"}:
        raise CatalystError("Claude access requires only access_token and expires_at; refresh credentials stay local.")
    validate_token(value["access_token"])
    if any(c in value["access_token"] for c in "'\"\\$`#"):
        raise CatalystError("Access token contains unsupported environment-file characters.")
    try:
        stamp = value["expires_at"]
        if not isinstance(stamp, str) or len(stamp) > 64 or any(ord(c) < 33 or ord(c) > 126 for c in stamp):
            raise ValueError
        expiry = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
            raise ValueError
    except (AttributeError, ValueError, TypeError, OverflowError):
        raise CatalystError("Claude access requires a future expires_at timestamp with a timezone.") from None


def provider_environment(provider, value):
    """Shared local/remote credential staging; values go only to private tmpfs."""
    if provider == "claude-subscription":
        validate_session_access(value)
        return {"TESTBED_CLAUDE_ACCESS_TOKEN": value["access_token"],
                "TESTBED_CLAUDE_ACCESS_TOKEN_EXPIRES_AT": value["expires_at"]}
    if provider in PROVIDER_ENV:
        return {PROVIDER_ENV[provider]: value}
    return {}


def validate_provider_access(document):
    if not isinstance(document, dict) or not document or set(document) - PROVIDERS:
        raise CatalystError("Provider access must map supported providers to temporary credentials.")
    for provider, value in document.items():
        if provider == "openai-chatgpt":
            validate_access(value)
        elif provider == "claude-subscription":
            validate_session_access(value)
        else:
            validate_token(value)
            if any(c in value for c in "'\"\\$`#"):
                raise CatalystError("Provider token contains unsupported environment-file characters.")
