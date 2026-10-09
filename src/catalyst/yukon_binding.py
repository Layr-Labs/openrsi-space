"""Bind stock Yukon's Pareto execution IDs using transient solver authentication."""
from __future__ import annotations

import json
import re

from .common import canonical
from .evaluator import APIError, identity
from .github_identity import SHA

PROTOCOL = "yukon-execution-binding-v1"


def bind_execution(store, auth, header, body):
    """Only Yukon's authenticated job response can establish an execution mapping."""
    if (not isinstance(body, dict)
            or set(body) != {"protocol", "job_id", "benchmark_id", "reference"}
            or body["protocol"] != PROTOCOL):
        raise APIError(400, "Malformed Yukon execution binding.")
    job_id, benchmark_id = identity(body["job_id"]), identity(body["benchmark_id"])
    reference = body["reference"]
    if not isinstance(reference, dict) or len(canonical(reference)) > 64 * 1024:
        raise APIError(400, "Invalid verification receipt.")
    key = header[7:] if isinstance(header, str) and header.startswith("Bearer ") else ""
    if not re.fullmatch(r"ykn_[A-Za-z0-9_-]{4,252}", key):
        raise APIError(401, "A Yukon API key is required for execution binding.")
    matches = [(repo_id, policy) for repo_id, policy in
               auth.github.config.get("repositories", {}).items()
               if policy.get("enabled") is True and policy.get("benchmark_id") == benchmark_id]
    if len(matches) != 1:
        raise APIError(403, "The Yukon benchmark has no unique authorized repository.")
    repo_id, policy = matches[0]
    # The key may only go to the same trusted origin used for solver login.
    if not auth.yukon or policy.get("yukon_api_url") != auth.yukon.api:
        raise APIError(403, "Yukon binding and login origins must match.")
    # GET /api/jobs/:id authenticates the key and permits only the job's account.
    document = auth.github.get_json(auth.yukon.api, f"/api/jobs/{job_id}", key)
    job = document.get("job") if isinstance(document, dict) else None
    if (not isinstance(job, dict) or job.get("id") != job_id
            or job.get("kind") != "submission_validation"
            or job.get("benchmarkId") != benchmark_id
            or job.get("status") not in {"queued", "running", "succeeded", "failed"}
            or not isinstance(job.get("input"), dict)):
        raise APIError(403, "Yukon job does not authorize this submission binding.")
    owner, submission_id = identity(job.get("accountId")), identity(job.get("submissionId"))
    execution_id = identity(job["input"].get("executionSubmissionId", submission_id))
    source_sha = job["input"].get("sourceRef")
    if (job["input"].get("sourceUrl") != f"https://github.com/{policy['repository']}"
            or not isinstance(source_sha, str) or not SHA.fullmatch(source_sha)):
        raise APIError(403, "Yukon job belongs to a different source repository.")
    evaluation_id = identity(reference.get("evaluation_id"))
    evaluated = store.get(evaluation_id)
    if evaluated["owner"] != owner:
        raise APIError(403, "Receipt belongs to another solver.")
    from .hosted import _verified_judgment
    _verified_judgment(evaluated, reference, policy["problem"], evaluated["request"]["judge"])
    binding = {
        "repository_id": repo_id, "execution_id": execution_id,
        "job_id": job_id, "benchmark_id": benchmark_id, "submission_id": submission_id,
        "owner_id": owner, "source_sha": source_sha, "reference": reference,
    }
    encoded = canonical(binding).decode()
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("""CREATE TABLE IF NOT EXISTS github_execution_bindings (
            repository_id TEXT NOT NULL, execution_id TEXT NOT NULL, binding TEXT NOT NULL,
            PRIMARY KEY(repository_id, execution_id))""")
        prior = db.execute("SELECT binding FROM github_execution_bindings "
                           "WHERE repository_id=? AND execution_id=?", (repo_id, execution_id)).fetchone()
        if prior and prior["binding"] != encoded:
            raise APIError(409, "This execution is already bound to different evidence.")
        db.execute("INSERT OR IGNORE INTO github_execution_bindings VALUES (?,?,?)",
                   (repo_id, execution_id, encoded))
    # No key, session, upstream job archive URL or other private job fields are stored.
    return {"protocol": PROTOCOL, "job_id": job_id, "execution_id": execution_id,
            "submission_id": submission_id, "benchmark_id": benchmark_id,
            "evaluation_id": evaluation_id}


def execution_binding(store, repository_id, execution_id):
    if store is None:
        return None
    with store.connect() as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                          "AND name='github_execution_bindings'").fetchone():
            return None
        row = db.execute("SELECT binding FROM github_execution_bindings "
                         "WHERE repository_id=? AND execution_id=?",
                         (repository_id, execution_id)).fetchone()
        return json.loads(row["binding"]) if row else None
