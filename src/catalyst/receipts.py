"""Receipt-only verification client; this module never submits an evaluation."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
import sys
import time

from .common import CatalystError, read_json, write_json
from .problems import initial_problems
from .remote import HTTPFailure, digest, endpoint, judge_input, solver_fetch

PROTOCOL = "remote-verification-receipt-v1"
RECEIPT_PATH = Path("verification.json")
SCORE_PATH = Path(".catalyst/yukon/score.json")

def retrieve_with_binding_wait(base, token, body):
    """Bounded read retries while a hosted execution's owner binding is registered."""
    seconds = 0
    if os.environ.get("GITHUB_ACTIONS") == "true":
        try:
            seconds = int(os.environ.get("CATALYST_RECEIPT_AUTH_WAIT_SECONDS", "0"))
        except ValueError:
            raise CatalystError("Invalid receipt authorization wait.") from None
        if not 0 <= seconds <= 60:
            raise CatalystError("Receipt authorization wait must be between 0 and 60 seconds.")
    deadline = time.monotonic() + seconds
    notified = False
    while True:
        try:
            return solver_fetch(base, "/verifications/retrieve", token, document=body)
        except HTTPFailure as error:
            remaining = deadline - time.monotonic()
            if error.status != 403 or seconds == 0 or remaining <= 0:
                raise
            if not notified:
                print("Waiting briefly for the hosted receipt authorization; no evaluation is started.",
                      file=sys.stderr, flush=True)
                notified = True
            time.sleep(min(2, remaining))


def problem_identity():
    return {"id": "ecdsa.fail", "version": digest(initial_problems())}


def read_receipt(path):
    try:
        # The path and its parents must not redirect the trusted workflow.
        for parent in (path, *path.parents):
            if parent.is_symlink():
                raise CatalystError("Verification receipt paths must not contain symlinks.")
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > 64 * 1024:
            raise CatalystError("Verification receipt must be a regular JSON file under 64 KiB.")
        reference = read_json(path)
    except FileNotFoundError:
        raise CatalystError(
            "Missing verification.json. Submit your harness with "
            "catalyst remote submit HARNESS_DIR --wait, then copy its receipt here.") from None
    if not isinstance(reference, dict):
        raise CatalystError("Verification receipt must be a JSON object.")
    return reference


def check_receipt(root=None):
    from .yukon import authentication
    root = (root or Path.cwd()).resolve()
    target = root / SCORE_PATH
    target.unlink(missing_ok=True)
    reference = read_receipt(root / RECEIPT_PATH)
    requested = judge_input(os.environ.get("YUKON_EVALUATION"))
    problem = problem_identity()
    token, _ = authentication()
    body = {"protocol": PROTOCOL, "reference": reference, "problem": problem, "judge": requested}
    result = json.loads(retrieve_with_binding_wait(endpoint(), token, body))
    if (not isinstance(result, dict) or result.get("protocol") != PROTOCOL
            or result.get("reference") != reference or result.get("problem") != problem
            or result.get("judge") != requested):
        raise CatalystError("Verification response does not match this receipt, problem and policy.")
    artifact = result.get("artifact")
    if (not isinstance(artifact, dict) or artifact.get("kind") != "harness-source"
            or not isinstance(artifact.get("sha256"), str)
            or not re.fullmatch(r"[a-f0-9]{64}", artifact["sha256"])
            or artifact["sha256"] != reference.get("source_digest")):
        raise CatalystError("Verification response omitted the verified harness identity.")
    judgment = result.get("judgment")
    if not isinstance(judgment, dict):
        raise CatalystError("Verification response omitted its judgment.")
    fields = requested["fields"]
    public = {"metrics": judgment.get("metrics", {})}
    if not isinstance(public["metrics"], dict):
        raise CatalystError("Verification metrics must be an object.")
    if fields["scores"]:
        import math
        scores = judgment.get("scores")
        if "scores" not in judgment or (scores is not None and (
                not isinstance(scores, list) or len(scores) != 2
                or any(type(value) not in (int, float) or not math.isfinite(value) for value in scores))):
            raise CatalystError("Verification response has an invalid Pareto tuple.")
        public["scores"] = scores
    if fields["validity"]:
        if type(judgment.get("valid")) is not bool:
            raise CatalystError("Verification response omitted validity.")
        public["valid"] = judgment["valid"]
        reason = judgment.get("reason")
        if reason is not None or not judgment["valid"]:
            if not isinstance(reason, str) or not reason.strip() or len(reason) > 4000:
                raise CatalystError("Verification response has an invalid validity reason.")
            public["reason"] = reason
    public["metrics"]["remoteVerification"] = {"problem": problem, "artifact": artifact}
    write_json(target, public)
    print(f"Verified receipt {reference.get('evaluation_id')}; no evaluation was started.", flush=True)
    return public
