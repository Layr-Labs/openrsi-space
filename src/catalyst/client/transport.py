"""Bounded HTTP, safe downloads and process-local Yukon login sessions."""
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from catalyst.common import CatalystError, canonical, read_json
from catalyst.contracts.results import evaluation_id

_solver_sessions = {}

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise CatalystError("Evaluator redirects are refused to protect authorization.")


def credential_url(url, *, model_access=False):
    """Validate before opening a connection or exchanging a solver login."""
    parts = urllib.parse.urlsplit(url)
    loopback = parts.scheme == "http" and parts.hostname in {"127.0.0.1", "localhost", "::1"}
    if (not parts.hostname or parts.username or parts.password or parts.fragment
            or (parts.scheme != "https" and not (loopback and not model_access))):
        raise CatalystError("Credentials require a trusted HTTPS evaluator endpoint; HTTP is only for local fixtures.")
    if model_access:
        route = parts.path.split("/")
        renewal = len(route) == 4 and route[:2] == ["", "evaluations"] and route[3] == "credentials"
        if renewal:
            evaluation_id(route[2])
        if parts.query or not (parts.path == "/evaluations" or renewal):
            raise CatalystError("Provider tokens require an HTTPS evaluation submission or credential-renewal endpoint.")


class HTTPFailure(CatalystError):
    def __init__(self, status, details=None):
        self.status = status
        messages = {
            'account_concurrency': 'Your account has reached its active-run limit; wait for a run to finish or cancel it.',
            'global_capacity': 'All evaluation slots are occupied; retry after a run finishes.',
            'submission_rate_limit': 'Too many new submissions in the short submission window.',
            'daily_quota': 'The operator-configured daily evaluation quota is reached.',
        }
        self.details = {}
        if (status == 429 and isinstance(details, dict) and isinstance(details.get('code'), str)
                and details['code'] in messages):
            self.details['code'] = details['code']
            if isinstance(details.get('scope'), str) and details['scope'] in {'account', 'global'}:
                self.details['scope'] = details['scope']
            for name in ('limit', 'current', 'retry_after_seconds'):
                value = details.get(name)
                if type(value) is int and 0 <= value <= 2**53:
                    self.details[name] = value
        message = f"Evaluator returned HTTP {status}"
        if self.details:
            message += ': ' + messages[self.details['code']]
            message += ' (' + ', '.join(f'{k}={v}' for k, v in self.details.items()) + ')'
        super().__init__(message + '; request remains resumable. Retry the same saved request ID.')


def fetch(url: str, token: str, *, document=None, limit=4 * 1024 * 1024, timeout=30,
          model_token=None, output=None, expected_sha256=None, expected_size=None) -> bytes:
    if token or model_token is not None:
        credential_url(url, model_access=model_token is not None)
    private_headers = {}
    if model_token is not None:
        from catalyst.credentials import TOKEN_HEADER, validate_token
        validate_token(model_token)
        private_headers[TOKEN_HEADER] = model_token
    request = urllib.request.Request(
        url, data=canonical(document) if document is not None else None,
        headers={**({"Authorization": f"Bearer {token}"} if token else {}),
                 "Content-Type": "application/json", **private_headers},
        method="POST" if document is not None else "GET",
    )
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            if output is None:
                content = response.read(limit + 1)
            else:
                import tempfile
                target = Path(output)
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = None
                try:
                    with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".artifact-", delete=False) as stream:
                        temporary = Path(stream.name)
                        hasher, size = hashlib.sha256(), 0
                        while chunk := response.read(1024 * 1024):
                            size += len(chunk)
                            if size > limit:
                                raise CatalystError("Artifact exceeds its declared download limit.")
                            hasher.update(chunk)
                            stream.write(chunk)
                    if size != expected_size or hasher.hexdigest() != expected_sha256:
                        raise CatalystError("Downloaded artifact does not match its verified checksum and size.")
                    temporary.replace(target)
                    temporary = None
                    return b""
                finally:
                    if temporary is not None:
                        temporary.unlink(missing_ok=True)
    except urllib.error.HTTPError as error:
        # Only display bounded, typed admission fields and local message text.
        # Never echo arbitrary error text, provider diagnostics or credentials.
        status, details = error.code, None
        try:
            if status == 429:
                body = error.read(8193)
                if len(body) <= 8192:
                    details = json.loads(body)
        except (ValueError, OSError, http.client.HTTPException):
            pass
        finally:
            error.close()
        raise HTTPFailure(status, details) from None
    except (urllib.error.URLError, http.client.HTTPException, OSError) as error:
        if isinstance(getattr(error, "reason", error), ssl.SSLCertVerificationError):
            raise CatalystError(
                "Evaluator TLS certificate verification failed; credentials were not sent. "
                "Check the evaluator URL, certificate and client trust store; do not disable TLS verification. "
                "The request remains resumable."
            ) from None
        raise CatalystError("Evaluator is unreachable; request remains resumable.") from None
    if len(content) > limit:
        raise CatalystError("Evaluator response exceeds the allowed size.")
    return content


def solver_fetch(base, route, bearer, *, document=None, limit=4 * 1024 * 1024, model_token=None,
                 output=None, expected_sha256=None, expected_size=None):
    if bearer or model_token is not None:
        credential_url(base + route, model_access=model_token is not None)
    private = {"model_token": model_token} if model_token is not None else {}
    if output is not None:
        private.update(output=output, expected_sha256=expected_sha256, expected_size=expected_size)
    if not bearer.startswith("ykn_"):
        return fetch(base + route, bearer, document=document, limit=limit, **private)
    parts = urllib.parse.urlsplit(base)
    if (parts.username or parts.password or parts.query or parts.fragment or not parts.hostname
            or (parts.scheme != "https" and not (
                parts.scheme == "http" and parts.hostname in {"127.0.0.1", "localhost", "::1"}))):
        raise CatalystError("Yukon login requires a trusted HTTPS evaluator endpoint.")
    cache_key = (base, hashlib.sha256(bearer.encode()).digest())
    for attempt in range(2):
        cached = _solver_sessions.get(cache_key)
        if cached is None or cached[1] <= time.monotonic():
            result = json.loads(fetch(base + "/auth/yukon", bearer,
                                      document={"protocol": "catalyst-yukon-session-v1"},
                                      limit=16 * 1024))
            if (not isinstance(result, dict) or result.get("protocol") != "catalyst-yukon-session-v1"
                    or not isinstance(result.get("access_token"), str)
                    or not re.fullmatch(r"cys_[A-Za-z0-9_.-]{1,4096}", result["access_token"])
                    or type(result.get("expires_in")) is not int
                    or not 60 <= result["expires_in"] <= 900):
                raise CatalystError("Evaluator returned an invalid login session.")
            evaluation_id(result.get("owner_id"))
            cached = (result["access_token"], time.monotonic() + result["expires_in"] - 30)
            if len(_solver_sessions) >= 8:
                _solver_sessions.clear()
            _solver_sessions[cache_key] = cached
        try:
            return fetch(base + route, cached[0], document=document, limit=limit, **private)
        except HTTPFailure as error:
            if error.status != 401 or attempt:
                raise
            # Authentication failed before dispatch (e.g. the server restarted).
            # Keep the same request body/operation key when renewing and retrying.
            _solver_sessions.pop(cache_key, None)


def endpoint() -> str:
    value = os.environ.get("CATALYST_EVALUATOR_URL", "").rstrip("/")
    parts = urllib.parse.urlsplit(value)
    if (not parts.hostname or parts.username or parts.password or parts.query or parts.fragment
            or (parts.scheme != "https"
                and not (parts.scheme == "http" and parts.hostname in {"127.0.0.1", "localhost", "::1"}))):
        raise CatalystError("Configure CATALYST_EVALUATOR_URL as the trusted HTTPS evaluator endpoint.")
    return value


def solver_token() -> str:
    bearer = (os.environ.get("YUKON_API_TOKEN") or os.environ.get("CATALYST_API_TOKEN")
              or os.environ.get("HILBERT_API_TOKEN") or os.environ.get("SUPABASE_ACCESS_TOKEN"))
    if not bearer:
        config_root = Path(os.environ.get("YUKON_CONFIG_DIR", str(Path.home() / ".config")))
        config_path = config_root / "yukon/config.json"
        if not config_path.exists() and not os.environ.get("YUKON_CONFIG_DIR"):
            config_path = config_root / "hilbert/config.json"
        config = read_json(config_path) if config_path.is_file() else {}
        bearer = config.get("token")
    if not isinstance(bearer, str) or not bearer or "\n" in bearer or "\r" in bearer:
        raise CatalystError("Log in with yukon login or set YUKON_API_TOKEN before requesting an evaluation.")
    return bearer
