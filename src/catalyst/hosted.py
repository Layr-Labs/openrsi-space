"""Private VM identities and read-only result retrieval by a trusted Yukon backend."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import secrets

from .common import CatalystError, open_bundle, read_json, write_json
from .evaluator import APIError, LocalIdentity, identity
from .local_run import initialize_ecdsa
from .remote import digest, judge_input, judgment, verification_reference

PROTOCOL = "catalyst-yukon-v1"


class ServiceIdentity(LocalIdentity):
    """Explicitly provisioned, hashed bearer tokens; no simulated workflow claims."""

    def __init__(self, config):
        if config.get("mode") != "service":
            raise CatalystError("Service authentication requires provisioned identities.")
        self.config = config

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
            hashlib.sha256(consumer.encode()).hexdigest(): {"kind": "yukon-service", "id": "yukon"},
        },
        "grants": old["grants"],
    })
    write_json(root / "client-tokens.json", {"solver": solver, "yukon": consumer, "owner_id": owner_id})
    (root / "client-tokens.json").chmod(0o600)
    return {**result, "evidence": "remote", "owner_id": owner_id}


def retrieve_for_yukon(store, evaluation_id, principal, body):
    """Compare backend-computed file hashes; never accept a solver's claimed scores."""
    if principal.get("kind") != "yukon-service":
        raise APIError(403, "A Yukon service identity is required.")
    required = {"protocol", "kind", "owner_id", "submission_id", "benchmark_id",
                "reference", "source_files", "evaluation", "judge"}
    if not isinstance(body, dict) or set(body) != required or body["protocol"] != PROTOCOL:
        raise APIError(400, "Malformed Yukon retrieval request.")
    if body["kind"] not in {"baseline", "submission"}:
        raise APIError(400, "Unsupported retrieval kind.")
    for key in ("owner_id", "submission_id", "benchmark_id"):
        identity(body[key])
    job = store.get(evaluation_id)
    if job["owner"] != body["owner_id"]:
        raise APIError(403, "Submission owner differs from evaluation owner.")
    if job["status"] != "completed" or job["request"]["evidence_mode"] != "remote":
        raise APIError(409, "A completed remote evaluation is required.")
    request, result = job["request"], job["result"]
    judge = judge_input(json.dumps(body["judge"]))
    snapshot, _ = open_bundle(base64.b64decode(request["source"]["archive_base64"]))
    if (body["source_files"] != snapshot["files"]
            or body["evaluation"] != request["evaluation"]
            or body["reference"] != verification_reference(result, request)
            or judge["policies"] != request["judge"]["policies"]):
        raise APIError(409, "Submitted source, configuration or reference differs from the verified evaluation.")
    # A retry may ask for a different field subset; it must retain the same source,
    # owner, policy and evaluation. Reading never creates an evaluation.
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
    return {"protocol": PROTOCOL, "evaluation_id": evaluation_id, "reference": body["reference"],
            "judgment": judgment(result, {**request, "judge": judge})}
