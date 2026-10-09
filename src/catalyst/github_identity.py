"""Authenticate GitHub workflows and resolve owners through stock Yukon APIs."""
from __future__ import annotations

import json
import re
import urllib.parse
import uuid

import jwt

from .common import CatalystError
from .evaluator import APIError, identity
from .remote import HTTPFailure, fetch

ISSUER = "https://token.actions.githubusercontent.com"
AUDIENCE = "catalyst-evaluator"
SHA = re.compile(r"^[a-f0-9]{40}$")
SUBMISSION_REF = re.compile(r"^refs/heads/submissions/([a-f0-9-]{36})$")


class GitHubIdentity:
    """Only configured repository identities can use the receipt lookup API."""

    def __init__(self, config, *, keys=None, get_json=None):
        self.config = config
        self.keys = keys or jwt.PyJWKClient(
            ISSUER + "/.well-known/jwks", cache_keys=True, timeout=10)
        self.get_json = get_json or self._get_json

    def authenticate(self, token):
        try:
            key = self.keys.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token, key, algorithms=["RS256"], audience=AUDIENCE, issuer=ISSUER,
                leeway=30, options={"require": [
                    "exp", "iat", "nbf", "iss", "aud", "sub", "repository",
                    "repository_id", "ref", "sha", "workflow_ref", "workflow_sha",
                    "run_id", "run_attempt", "event_name",
                ]})
        except (jwt.PyJWTError, ValueError, TypeError, OSError):
            raise APIError(401, "GitHub workflow authentication failed.") from None
        repository_id = claims.get("repository_id")
        if not isinstance(repository_id, str):
            raise APIError(403, "Unregistered GitHub repository.")
        policy = self.config.get("repositories", {}).get(repository_id)
        if not isinstance(policy, dict) or policy.get("enabled") is not True:
            raise APIError(403, "Remote verification is not enabled for this repository.")
        repository, ref, sha = claims["repository"], claims["ref"], claims["sha"]
        workflow = policy.get("workflow", ".github/workflows/benchmark.yml")
        if (repository != policy.get("repository")
                or claims["event_name"] != "workflow_dispatch"
                or not isinstance(ref, str) or not ref.startswith("refs/heads/")
                or not isinstance(sha, str) or not SHA.fullmatch(sha)
                or claims["workflow_sha"] != sha
                or claims["workflow_ref"] != f"{repository}/{workflow}@{ref}"
                or any(not isinstance(claims[key], str) or not claims[key].isdigit()
                       for key in ("run_id", "run_attempt"))):
            raise APIError(403, "Workflow identity does not match the configured challenge.")
        # GitHub can also include job_workflow_* for the direct workflow.
        # Accept that self-reference, but never a different reusable judge.
        if any(key in claims and claims[key] != claims[workflow_key]
               for key, workflow_key in (
                   ("job_workflow_ref", "workflow_ref"),
                   ("job_workflow_sha", "workflow_sha"),
               )):
            raise APIError(403, "Job workflow identity does not match the configured challenge.")
        return {"kind": "github-actions", "claims": claims, "policy": policy}

    @staticmethod
    def _get_json(base, path, token):
        parts = urllib.parse.urlsplit(base)
        if (parts.scheme != "https" or not parts.hostname or parts.username
                or parts.password or parts.query or parts.fragment):
            raise APIError(503, "Configure a trusted HTTPS Yukon API.")
        try:
            return json.loads(fetch(base.rstrip("/") + path, token or "", limit=1024 * 1024))
        except HTTPFailure as error:
            if error.status == 404:
                raise APIError(403, "Yukon identity was not found; register the Pareto job with catalyst yukon-bind.") from None
            raise APIError(503, f"Yukon identity lookup returned HTTP {error.status}.") from None
        except (CatalystError, ValueError):
            raise APIError(503, "Cannot establish the Yukon submission identity.") from None

    def receipt_context(self, principal, reference, *, store=None):
        """A workflow cannot claim its owner, benchmark, problem or submission ID."""
        claims, policy = principal["claims"], principal["policy"]
        ref = claims["ref"]
        matched = SUBMISSION_REF.fullmatch(ref)
        if matched:
            submission_id = matched.group(1)
            identity(submission_id)
            benchmark_id = policy.get("benchmark_id")
            if not benchmark_id:
                raise APIError(403, "The repository has no authorized Yukon benchmark.")
            identity(benchmark_id)
            from .yukon_binding import execution_binding
            bound = execution_binding(store, claims["repository_id"], submission_id)
            if bound:
                if bound["benchmark_id"] != benchmark_id or bound["reference"] != reference:
                    raise APIError(403, "Execution binding does not match this benchmark and receipt.")
                if bound.get("revision") is not None and bound["revision"] != claims["sha"]:
                    raise APIError(403, "Replay revision differs from its operator authorization.")
                submission_id = bound["submission_id"]
            document = self.get_json(
                policy["yukon_api_url"], f"/api/submissions/{submission_id}",
                policy.get("yukon_api_token"))
            submission = document.get("submission") if isinstance(document, dict) else None
            if (not isinstance(submission, dict) or submission.get("id") != submission_id
                    or submission.get("benchmarkId") != benchmark_id
                    or submission.get("status") == "cancelled"):
                raise APIError(403, "Workflow does not identify an authorized Yukon submission.")
            owner_id = submission.get("solverAccountId")
            identity(owner_id)
            if bound and owner_id != bound["owner_id"]:
                raise APIError(403, "Yukon submission owner differs from the execution binding.")
        else:
            # Initial import has no submission/account input. Only this exact
            # operator-approved baseline revision and receipt may pass.
            baseline = policy.get("baseline", {})
            if (ref != baseline.get("ref") or claims["sha"] != baseline.get("sha")
                    or reference.get("evaluation_id") != baseline.get("evaluation_id")):
                raise APIError(403, "Workflow is neither a submission nor an approved baseline.")
            benchmark_id = baseline.get("binding_id")
            submission_id = benchmark_id
            owner_id = baseline.get("owner_id")
            identity(benchmark_id)
            identity(owner_id)
        return {
            "consumer": f"github:{claims['repository_id']}",
            "kind": "submission" if matched else "baseline",
            "owner_id": owner_id, "benchmark_id": benchmark_id,
            "submission_id": submission_id, "revision": claims["sha"],
            # Each revalidation has its own immutable execution. Keep the original
            # submission identity for owner checks and audit, without overwriting
            # the earlier execution's receipt binding.
            "execution_id": matched.group(1) if matched else str(
                uuid.uuid5(uuid.UUID(benchmark_id), claims["sha"])),
            "problem": policy.get("problem"),
            "workflow": {key: claims[key] for key in
                         ("repository_id", "repository", "ref", "sha", "run_id", "run_attempt")},
        }
