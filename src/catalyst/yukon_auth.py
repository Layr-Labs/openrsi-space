"""Yukon login exchange. User keys and session signing keys live only in memory."""
from __future__ import annotations

import json
import re
import secrets
import threading
import time
from urllib.parse import urlsplit

import jwt

from .common import CatalystError, read_json, write_json
from .evaluator import APIError, identity
from .remote import HTTPFailure, fetch, validate_evaluation_config

PROTOCOL = "catalyst-yukon-session-v1"
PREFIX = "cys_"
AUDIENCE = "catalyst-solver"
SESSION_SECONDS = 900


class YukonLogin:
    def __init__(self, config):
        self.api = config["api_url"]
        parts = urlsplit(self.api)
        if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
                or parts.query or parts.fragment or parts.path not in ("", "/")):
            raise CatalystError("Yukon login requires an operator-configured HTTPS API origin.")
        self.api = self.api.rstrip("/")
        self.signing_key = secrets.token_bytes(32)
        self.inflight = threading.BoundedSemaphore(4)

    def exchange(self, header):
        key = header[7:] if isinstance(header, str) and header.startswith("Bearer ") else ""
        if not re.fullmatch(r"ykn_[A-Za-z0-9_-]{4,252}", key):
            raise APIError(401, "A Yukon API key is required.")
        if not self.inflight.acquire(blocking=False):
            raise APIError(429, "Login is busy; retry shortly.")
        try:
            try:
                response = json.loads(fetch(self.api + "/api/me", key, limit=64 * 1024, timeout=10))
            except HTTPFailure as error:
                if error.status in (401, 403):
                    raise APIError(401, "Yukon rejected this API key.") from None
                raise APIError(503, "Yukon authentication is temporarily unavailable.") from None
            except (CatalystError, ValueError):
                raise APIError(503, "Yukon authentication is temporarily unavailable.") from None
            try:
                owner = identity(response["account"]["id"])
            except (APIError, KeyError, TypeError):
                raise APIError(503, "Yukon returned an invalid account identity.") from None
            issued = int(time.time())
            claims = {"iss": self.api, "aud": AUDIENCE, "sub": owner,
                      "scope": "solver", "iat": issued, "exp": issued + SESSION_SECONDS}
            token = PREFIX + jwt.encode(claims, self.signing_key, algorithm="HS256")
            return {"protocol": PROTOCOL, "access_token": token, "owner_id": owner,
                    "expires_in": SESSION_SECONDS}
        finally:
            # No key or upstream account/key response is retained in object state.
            self.inflight.release()

    def authenticate(self, token):
        try:
            claims = jwt.decode(token[len(PREFIX):], self.signing_key, algorithms=["HS256"],
                                issuer=self.api, audience=AUDIENCE,
                                options={"require": ["sub", "iat", "exp", "scope"]})
            if claims["scope"] != "solver":
                raise ValueError
            owner = identity(claims["sub"])
        except (jwt.PyJWTError, APIError, ValueError, TypeError):
            raise APIError(401, "Solver session expired or invalid; log in again.") from None
        return {"kind": "yukon-solver", "owner": owner, "authentication": "yukon"}


def configure_yukon_login(auth_file, yukon_api, worker_file):
    """Enable Yukon users under the model-disabled MVP policy; no user key input."""
    login = YukonLogin({"api_url": yukon_api})
    config, worker = read_json(auth_file), read_json(worker_file)
    if config.get("mode") != "service" or worker.get("mode") != "remote" or worker.get("model_access") != "disabled":
        raise CatalystError("Yukon onboarding currently requires the model-disabled remote worker.")
    previous = config.get("yukon_login", {}).get("api_url")
    if previous and previous != login.api:
        raise CatalystError("Changing the Yukon identity issuer requires an explicit account migration.")
    evaluation = {"schema_version": 3, "llm_access": {"grant_id": "grant_local_ecdsa"},
                  "model": {"provider": "openai", "name": "gpt-5.6-sol"},
                  "max_model_credits": 20,
                  "limits": {"max_model_tokens": 100000, "max_seconds": 60}}
    validate_evaluation_config(evaluation)
    config["yukon_login"] = {"api_url": login.api}
    config.setdefault("solver_policy", {
        "evaluation": evaluation, "max_active_per_owner": 1,
        "max_active_total": 8, "max_daily_per_owner": 10,
    })
    # Disable legacy solver passwords, preserving independent consumer/OIDC access.
    config["tokens"] = {key: value for key, value in config.get("tokens", {}).items()
                        if value.get("kind") != "yukon-solver"}
    temporary = auth_file.with_name(auth_file.name + ".new")
    write_json(temporary, config)
    temporary.chmod(0o600)
    temporary.replace(auth_file)
    return {"yukon_api": login.api, "session_seconds": SESSION_SECONDS,
            "solver_policy": config["solver_policy"], "restart_required": True}
