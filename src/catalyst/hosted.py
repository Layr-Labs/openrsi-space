"""Private VM identities and read-only result retrieval by a trusted Yukon backend."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import secrets
import re

from .common import CatalystError, canonical, read_json, write_json
from .evaluator import APIError, LocalIdentity, identity
from .local_run import initialize_ecdsa
from .remote import digest, judge_input, judgment, verification_reference

PROTOCOL = "yukon-remote-verification-v1"
LEGACY_PROTOCOL = "catalyst-yukon-v2"
OBJECTIVES = [{"name": "ecdsaPerformance", "direction": "-"},
              {"name": "modelCreditsAtBest", "direction": "-"}]


class ServiceIdentity(LocalIdentity):
    """Explicitly provisioned, hashed bearer tokens; no simulated workflow claims."""

    def __init__(self, config):
        if config.get("mode") != "service":
            raise CatalystError("Service authentication requires provisioned identities.")
        self.config = config
        from .github_identity import GitHubIdentity
        self.github = GitHubIdentity(config.get("github", {}))

    def authenticate(self, header):
        try:
            return super().authenticate(header)
        except APIError:
            token = header[7:] if isinstance(header, str) and header.startswith("Bearer ") else ""
            if not self.config.get("github") or len(token) > 20_000 or token.count(".") != 2:
                raise APIError(401, "Authentication required.") from None
            return self.github.authenticate(token)

    def workflow_context(self, principal, context):
        raise APIError(403, "Use the authenticated Yukon result endpoint.")


def initialize_remote(root: Path, dungeness: Path, owner_id: str):
    identity(owner_id)
    result = initialize_ecdsa(root, dungeness)
    root = root.resolve()
    config = read_json(root / "worker.json")
    config["mode"] = "remote"
    write_json(root / "worker.json", config)
    old = read_json(root / "auth.json")
    for grant in old["grants"].values():
        grant["owner"] = owner_id
    solver, consumer = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    write_json(root / "auth.json", {
        "mode": "service",
        "tokens": {
            hashlib.sha256(solver.encode()).hexdigest(): {"kind": "yukon-solver", "owner": owner_id},
            hashlib.sha256(consumer.encode()).hexdigest(): {
                "kind": "yukon-service", "id": "yukon", "benchmarks": {}},
        },
        "grants": old["grants"],
    })
    write_json(root / "client-tokens.json", {"solver": solver, "yukon": consumer, "owner_id": owner_id})
    (root / "client-tokens.json").chmod(0o600)
    return {**result, "evidence": "remote", "owner_id": owner_id}


def configure_github(store, auth_file, *, repository, repository_id, yukon_api,
                     baseline_evaluation, baseline_sha, benchmark_id=None):
    """Explicit operator provisioning; preserve tokens, jobs and other repositories."""
    from urllib.parse import urlsplit
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise CatalystError("Use an exact GitHub owner/repository.")
    if not repository_id.isdigit() or not re.fullmatch(r"[a-f0-9]{40}", baseline_sha):
        raise CatalystError("A numeric repository ID and exact baseline Git commit are required.")
    parts = urlsplit(yukon_api)
    if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
            or parts.query or parts.fragment or parts.path not in ("", "/")):
        raise CatalystError("Use the trusted HTTPS Yukon API origin.")
    if benchmark_id:
        identity(benchmark_id)
    job = store.get(baseline_evaluation)
    if job["status"] != "completed" or job["request"]["evidence_mode"] != "remote":
        raise CatalystError("Baseline must be an existing completed remote evaluation.")
    config = read_json(auth_file)
    if config.get("mode") != "service":
        raise CatalystError("GitHub authentication requires service mode.")
    repos = config.setdefault("github", {}).setdefault("repositories", {})
    previous = repos.get(repository_id, {})
    if previous and previous.get("repository") != repository:
        raise CatalystError("Repository ID was previously provisioned with a different name.")
    import uuid
    problem_set = job["request"]["problem_set"]
    if len(problem_set) != 1:
        raise CatalystError("Expected one verified Catalyst problem.")
    policy = {**previous, "enabled": True, "repository": repository,
              "workflow": ".github/workflows/benchmark.yml",
              "yukon_api_url": yukon_api.rstrip("/"),
              "problem": {"id": problem_set[0]["id"], "version": digest(problem_set)},
              "baseline": {"binding_id": previous.get("baseline", {}).get("binding_id", str(uuid.uuid4())),
                           "ref": f"refs/heads/yukon/baseline/{baseline_sha}", "sha": baseline_sha,
                           "owner_id": job["owner"], "evaluation_id": baseline_evaluation}}
    if benchmark_id:
        policy["benchmark_id"] = benchmark_id
    repos[repository_id] = policy
    temporary = auth_file.with_name(auth_file.name + ".new")
    write_json(temporary, config)
    temporary.chmod(0o600)
    temporary.replace(auth_file)
    return {"repository": repository, "repository_id": repository_id,
            "benchmark_id": policy.get("benchmark_id"), "baseline_sha": baseline_sha,
            "restart_required": True}


def retrieve_for_yukon(store, evaluation_id, principal, body):
    """Compatibility for the already deployed Catalyst-specific v2 consumer."""
    judgment_result = _retrieve(store, evaluation_id, principal, body, legacy=True)
    return {"protocol": LEGACY_PROTOCOL, "evaluation_id": evaluation_id,
            "reference": body["reference"], "judgment": judgment_result}


def retrieve_verification(store, principal, body):
    """Implement Yukon's project-independent stored verification contract."""
    judgment_result = _retrieve(store, None, principal, body)
    return {"protocol": PROTOCOL, "request": body,
            "artifact": {"kind": "harness-source",
                         "sha256": judgment_result["metrics"]["sourceDigest"]},
            "judgment": judgment_result}


def retrieve_receipt(store, auth, principal, body):
    """The challenge workflow authenticates; stock Yukon consumes its score artifact."""
    from .receipts import PROTOCOL as RECEIPT_PROTOCOL
    if (not isinstance(body, dict) or set(body) != {"protocol", "reference", "problem", "judge"}
            or body["protocol"] != RECEIPT_PROTOCOL):
        raise APIError(400, "Malformed verification receipt request.")
    reference = body["reference"]
    if not isinstance(reference, dict) or len(canonical(reference)) > 64 * 1024:
        raise APIError(400, "Invalid verification receipt.")
    evaluation_id = reference.get("evaluation_id")
    identity(evaluation_id)
    job = store.get(evaluation_id)
    if principal.get("kind") == "yukon-solver":
        if principal.get("owner") != job["owner"]:
            raise APIError(403, "Receipt belongs to another solver.")
        public = _verified_judgment(job, reference, body["problem"], body["judge"], allow_local=True)
    elif principal.get("kind") == "github-actions" and isinstance(auth, ServiceIdentity):
        context = auth.github.receipt_context(principal, reference)
        if body["problem"] != context["problem"]:
            raise APIError(409, "Requested problem differs from the authorized challenge.")
        public = _retrieve(store, None, {
            "kind": "yukon-service", "id": context["consumer"],
            "benchmarks": {context["benchmark_id"]: {"enabled": True, "problem": context["problem"]}},
        }, {
            "protocol": PROTOCOL, "kind": context["kind"], "owner_id": context["owner_id"],
            "benchmark_id": context["benchmark_id"], "benchmark_revision": context["revision"],
            "submission_id": context["submission_id"], "problem": body["problem"],
            "reference": reference, "objectives": OBJECTIVES, "judge": body["judge"],
        })
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""CREATE TABLE IF NOT EXISTS github_retrievals (
                repository_id TEXT NOT NULL, run_id TEXT NOT NULL, run_attempt TEXT NOT NULL,
                evaluation_id TEXT NOT NULL, context TEXT NOT NULL,
                PRIMARY KEY(repository_id, run_id, run_attempt))""")
            workflow = context["workflow"]
            key = tuple(workflow[k] for k in ("repository_id", "run_id", "run_attempt"))
            encoded = canonical({"workflow": workflow, "submission_id": context["submission_id"],
                                 "benchmark_id": context["benchmark_id"]}).decode()
            prior = db.execute("SELECT evaluation_id, context FROM github_retrievals "
                               "WHERE repository_id=? AND run_id=? AND run_attempt=?", key).fetchone()
            if prior and (prior["evaluation_id"] != evaluation_id or prior["context"] != encoded):
                raise APIError(409, "This workflow run is bound to different evidence.")
            db.execute("INSERT OR IGNORE INTO github_retrievals VALUES (?,?,?,?,?)",
                       (*key, evaluation_id, encoded))
    else:
        raise APIError(403, "A solver or configured GitHub workflow identity is required.")
    artifact = {"kind": "harness-source", "sha256": job["request"]["source"]["digest"]}
    public["metrics"]["remoteVerification"] = {"problem": body["problem"], "artifact": artifact}
    return {"protocol": RECEIPT_PROTOCOL, "reference": reference, "problem": body["problem"],
            "judge": body["judge"], "artifact": artifact, "judgment": public}


def _verified_judgment(job, reference, problem, requested, *, allow_local=False):
    if job["status"] != "completed" or (not allow_local and job["request"]["evidence_mode"] != "remote"):
        raise APIError(409, "A completed remote evaluation is required.")
    request, result = job["request"], job["result"]
    if (len(request["problem_set"]) != 1
            or problem != {"id": request["problem_set"][0]["id"],
                           "version": digest(request["problem_set"])}):
        raise APIError(409, "Verified evaluation belongs to a different problem or version.")
    if not isinstance(requested, dict) or set(requested) != {"policies", "fields"}:
        raise APIError(400, "Malformed judgment request.")
    judge = judge_input(json.dumps(requested))
    if reference != verification_reference(result, request) or judge["policies"] != request["judge"]["policies"]:
        raise APIError(409, "Receipt or policies differ from the verified evaluation.")
    return judgment(result, {**request, "judge": judge})


def _retrieve(store, evaluation_id, principal, body, legacy=False):
    """Resolve an owner-bound receipt against retained evidence, never claimed scores."""
    if principal.get("kind") != "yukon-service":
        raise APIError(403, "A Yukon service identity is required.")
    required = {"protocol", "kind", "owner_id", "submission_id", "benchmark_id",
                "reference", "judge"}
    if not legacy:
        required |= {"benchmark_revision", "objectives", "problem"}
    if (not isinstance(body, dict) or set(body) != required
            or body["protocol"] != (LEGACY_PROTOCOL if legacy else PROTOCOL)):
        raise APIError(400, "Malformed Yukon retrieval request.")
    if body["kind"] not in {"baseline", "submission"}:
        raise APIError(400, "Unsupported retrieval kind.")
    for key in ("owner_id", "submission_id", "benchmark_id"):
        identity(body[key])
    # Token possession alone is insufficient. The service operator explicitly
    # scopes this consumer to each Yukon benchmark and immutable problem version.
    allowed = principal.get("benchmarks", {})
    authorization = allowed.get(body["benchmark_id"]) if isinstance(allowed, dict) else None
    if not isinstance(authorization, dict) or authorization.get("enabled") is not True:
        raise APIError(403, "Remote verification is not enabled for this benchmark.")
    problem = authorization.get("problem")
    if (not isinstance(problem, dict) or set(problem) != {"id", "version"}
            or any(not isinstance(value, str) or not 1 <= len(value) <= 256
                   for value in problem.values())):
        raise APIError(403, "Benchmark problem binding is not configured.")
    if not legacy:
        if body["problem"] != problem:
            raise APIError(409, "Requested problem differs from the authorized benchmark.")
        if (not isinstance(body["benchmark_revision"], str)
                or not 1 <= len(body["benchmark_revision"]) <= 1024):
            raise APIError(400, "A pinned benchmark revision is required.")
        if body["objectives"] != OBJECTIVES:
            raise APIError(409, "Unsupported objective names, order or directions.")
        # Only the service interprets the receipt. Yukon does not know this
        # evaluation ID, evidence mode, source hashes or pricing schema.
        reference = body["reference"]
        if not isinstance(reference, dict) or len(canonical(reference)) > 64 * 1024:
            raise APIError(400, "Invalid verification receipt.")
        evaluation_id = reference.get("evaluation_id")
        if not isinstance(evaluation_id, str):
            raise APIError(409, "Unrecognized verification receipt.")
        try:
            identity(evaluation_id)
        except APIError:
            raise APIError(409, "Unrecognized verification receipt.") from None
    job = store.get(evaluation_id)
    if job["owner"] != body["owner_id"]:
        raise APIError(403, "Submission owner differs from evaluation owner.")
    public = _verified_judgment(job, body["reference"], problem, body["judge"])
    # A retry may ask for a different field subset; it must retain the same source,
    # owner, policy, benchmark revision, objective order and evaluation.
    # Reading never creates an evaluation.
    binding = digest({key: value for key, value in body.items() if key != "judge"})
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("""CREATE TABLE IF NOT EXISTS yukon_retrievals (
            consumer TEXT NOT NULL, benchmark_id TEXT NOT NULL, submission_id TEXT NOT NULL,
            evaluation_id TEXT NOT NULL, binding TEXT NOT NULL,
            PRIMARY KEY(consumer, benchmark_id, submission_id))""")
        previous = db.execute(
            "SELECT binding FROM yukon_retrievals WHERE consumer=? AND benchmark_id=? AND submission_id=?",
            (principal["id"], body["benchmark_id"], body["submission_id"])).fetchone()
        if previous and previous["binding"] != binding:
            raise APIError(409, "This Yukon submission is already bound to another evaluation.")
        db.execute("INSERT OR IGNORE INTO yukon_retrievals VALUES (?,?,?,?,?)",
                   (principal["id"], body["benchmark_id"], body["submission_id"], evaluation_id, binding))
    return public
