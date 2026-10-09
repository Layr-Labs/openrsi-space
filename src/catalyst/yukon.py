"""Thin Yukon adapter over the shared Catalyst verification-service client."""
from __future__ import annotations

import json
import os
from pathlib import Path
import urllib.parse
import uuid

from .common import CatalystError, read_json, write_json
from .problems import clone_problem, initial_problems, validate_workspace
from .remote import (
    HTTPFailure, RemoteClient, bound_result, digest, endpoint, fetch, judge_input, judgment,
    request_body, solver_token, verification_reference,
)


def setup_problems(root: Path) -> None:
    """Download the pinned ECDSA workspace without discarding edits/caches."""
    for problem in initial_problems():
        destination = root / "problems" / problem["id"]
        if destination.exists():
            validate_workspace(problem, destination)
        else:
            clone_problem(problem["id"], destination)
        print(f"{problem['title']}: {destination}", flush=True)
    print("Work locally on submission/. Problem setup/check commands are in docs/executable-harness.md.")



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



def publish_verified(score_path: Path, reference_path: Path, body: dict, base: str, bearer: str) -> dict:
    """Workflow resolves an existing remote observation without another paid run."""
    if not reference_path.is_file():
        raise CatalystError("Submission requires a verification reference; run catalyst remote submit --wait or yukon run.")
    reference = read_json(reference_path)
    try:
        identity = reference["evaluation_id"]
        if str(uuid.UUID(identity)) != identity:
            raise ValueError
    except (ValueError, TypeError, KeyError, AttributeError):
        raise CatalystError("Invalid remote verification reference.") from None
    if (not isinstance(reference, dict) or type(reference.get("schema_version")) is not int
            or reference.get("schema_version") != 2
            or reference.get("source_digest") != body["source"]["digest"]
            or reference.get("evaluation_config_digest") != digest(body["evaluation"])
            or reference.get("problem_set_digest") != digest(body["problem_set"])
            or reference.get("policies_digest") != digest(body["judge"]["policies"])):
        raise CatalystError("Remote verification does not match this source/model/budget/problem policy; evaluate again.")
    if reference.get("pricing_digest") != digest(body["pricing"]):
        raise CatalystError("Remote verification does not match the pinned pricing schedule; evaluate again.")
    # The server must authorize the evaluation's owner against the queued Yukon
    # submission, then bind the exact candidate source. A receipt is not proof.
    result = json.loads(fetch(f"{base}/evaluations/{identity}/submissions", bearer, document=body))
    bound_result(result, body, identity, original_request=False)
    if reference != verification_reference(result, body):
        raise CatalystError("Remote verification reference disagrees with the server's immutable result.")
    artifact = judgment(result, body)
    write_json(score_path, artifact)
    print(f"Published existing remote evaluation {identity}; no additional evaluation requested.", flush=True)
    return artifact


def run_remote(state: Path) -> dict:
    root = Path.cwd()
    score_path = root / ".catalyst/yukon/score.json"
    score_path.unlink(missing_ok=True)
    judge = judge_input(os.environ.get("YUKON_EVALUATION"))
    bearer, context = authentication()
    if context["kind"] == "github-actions":
        base = endpoint()
        body = request_body(root / "submission", base, judge=judge, context=context)
        return publish_verified(score_path, root / "submission/verification.json", body, base, bearer)
    client = RemoteClient(state, bearer=bearer)
    accepted = client.submit(root / "submission", judge=judge)
    identity = accepted["evaluation_id"]
    print(f"Remote evaluation {identity}; source {accepted['source_digest'][:12]}", flush=True)
    artifact = client.wait(identity)
    client.export_reference(identity, root / "submission")
    write_json(score_path, artifact)
    print(f"Verified remote judgment: {score_path}", flush=True)
    return artifact
