"""Thin Yukon adapter over the shared Catalyst verification-service client."""
from __future__ import annotations

import json
import os
from pathlib import Path
import urllib.parse

from .common import CatalystError
from .problems import clone_problem, initial_problems, validate_workspace
from .remote import HTTPFailure, fetch, solver_token


def setup_problems(root: Path) -> None:
    """Download the pinned ECDSA workspace without discarding edits/caches."""
    for problem in initial_problems():
        destination = root / "problems" / problem["id"]
        if destination.exists():
            validate_workspace(problem, destination)
        else:
            clone_problem(problem["id"], destination)
        print(f"{problem['title']}: {destination}", flush=True)
    print("Create your harness in a separate directory. See docs/executable-harness.md for local checks.")



def authentication() -> tuple[str, dict]:
    if os.environ.get("GITHUB_ACTIONS") == "true":
        required = ("GITHUB_REPOSITORY", "GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT")
        if any(not os.environ.get(key) for key in required):
            raise CatalystError("Missing GitHub evaluation identity.")
        oidc_url = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL", "")
        oidc_token = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "")
        parts = urllib.parse.urlsplit(oidc_url)
        if parts.scheme != "https" or parts.username or parts.password or not parts.hostname or not oidc_token:
            raise CatalystError("GitHub OIDC requires workflow id-token: write permission.")
        url = oidc_url + ("&" if parts.query else "?") + urllib.parse.urlencode({"audience": "catalyst-evaluator"})
        try:
            bearer = json.loads(fetch(url, oidc_token))["value"]
        except HTTPFailure as error:
            raise CatalystError(f"GitHub OIDC token request failed (HTTP {error.status}).") from None
        context = {"kind": "github-actions", "repository": os.environ["GITHUB_REPOSITORY"],
                   "commit": os.environ["GITHUB_SHA"], "run_id": os.environ["GITHUB_RUN_ID"],
                   "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"]}
    else:
        bearer = solver_token()
        context = {"kind": "yukon-solver"}
    if not isinstance(bearer, str) or not bearer or "\n" in bearer or "\r" in bearer:
        raise CatalystError("Invalid evaluation authentication token.")
    return bearer, context
