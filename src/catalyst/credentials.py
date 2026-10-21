"""Temporary credential encoding for the HTTPS client; refresh tokens stay local."""
import base64
import json
from pathlib import Path
from .common import CatalystError, canonical
from .protocol import APIError
from .provider_profiles import PROFILES, BUILTINS

TEMPORARY_GRANT = "grant_temporary_provider"
TOKEN_HEADER = "X-Catalyst-Model-Token"
MAX_TOKEN_BYTES = 8192
PROVIDERS = BUILTINS | PROFILES.keys()
# Read historical configurations without re-enabling their credentials or execution.
RETIRED_PROVIDERS = frozenset({"kimi-code", "moonshot"})

def require_active_models(models):
    for model in models:
        if model["provider"] in RETIRED_PROVIDERS:
            raise CatalystError("Kimi Code and direct Moonshot access are retired; choose a supported provider.")

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

def validate_provider_access(document):
    if not isinstance(document, dict) or not document or set(document) - PROVIDERS:
        raise CatalystError("Provider access must map supported providers to temporary credentials.")
    for provider, value in document.items():
        if provider == "openai-chatgpt":
            validate_access(value)
        elif PROFILES.get(provider, {}).get('credential_kind') == 'session-token':
            validate_session_access(value)
        else:
            validate_token(value)
            if any(c in value for c in "'\"\\$`#"):
                raise CatalystError("Provider token contains unsupported environment-file characters.")


def validate_session_access(value):
    from datetime import datetime, timezone
    if not isinstance(value, dict) or set(value) != {'access_token', 'expires_at'}:
        raise CatalystError('Subscription access requires only a temporary access token and expiry.')
    validate_token(value['access_token'])
    if value['access_token'].startswith('xai-') or any(c in value['access_token'] for c in "'\"\\$`#"):
        raise CatalystError('Expected a subscription session token, not an API key.')
    try:
        stamp = value['expires_at']
        if not isinstance(stamp, str) or not 20 <= len(stamp) <= 40 or any(ord(c) < 33 or ord(c) > 126 for c in stamp):
            raise ValueError
        expiry = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
        if expiry.tzinfo is None or expiry.timestamp() <= datetime.now(timezone.utc).timestamp() + 60:
            raise ValueError
    except (ValueError, TypeError, AttributeError, OverflowError):
        raise CatalystError('Grok session is expired or near expiry; run grok login --device-auth locally.') from None


def grok_access(path):
    """Read a first-party CLI session, never export refresh tokens or identity data."""
    from datetime import datetime, timedelta
    try:
        with Path(path).expanduser().open('rb') as stream:
            raw = stream.read(128 * 1024 + 1)
        if len(raw) > 128 * 1024:
            raise ValueError
        document = json.loads(raw)
        if not isinstance(document, dict):
            raise ValueError
        candidates = []
        for scope, entry in document.items():
            if not isinstance(entry, dict):
                continue
            first_party = (scope.startswith('https://auth.x.ai::')
                           and entry.get('oidc_issuer', '').rstrip('/') == 'https://auth.x.ai'
                           and entry.get('auth_mode') in {'oidc', 'external'})
            legacy = scope == 'https://accounts.x.ai/sign-in' and entry.get('auth_mode') in {'grok', 'web_login'}
            if not (first_party or legacy):
                continue
            expiry = entry.get('expires_at')
            if not expiry:
                expiry = (datetime.fromisoformat(entry['create_time'].replace('Z', '+00:00'))
                          + timedelta(days=30)).isoformat()
            access = {'access_token': entry['key'], 'expires_at': expiry}
            try:
                validate_session_access(access)
            except (CatalystError, APIError):
                continue
            candidates.append(access)
        # Never silently choose a different account/team or API-key credential.
        if len(candidates) != 1:
            raise ValueError
        return candidates[0]
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise CatalystError('Select a Grok auth.json with exactly one unexpired first-party session; '
                            'run grok login --device-auth locally. Refresh credentials stay local.') from None


def encode_grok_access(path):
    return encode_provider_access({'grok-subscription': grok_access(path)})

