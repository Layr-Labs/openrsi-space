"""Bound result validation, score projection and immutable receipt references."""
import hashlib
import json
import uuid
from catalyst.common import CatalystError, canonical
from .harness import IMAGE_RE
from .accounting import LEGACY_VALIDITY, SCORING, VALIDITY, evaluation_models, project_observation

PROTOCOL = "catalyst-evaluation-v3"
PENDING = {"queued", "awaiting_credentials", "building", "running", "verifying"}
TERMINAL = {"completed", "failed", "cancelled"}

def digest(document) -> str:
    return hashlib.sha256(canonical(document)).hexdigest()


def judge_input(value: str | None) -> dict:
    default = {"policies": {"scoring": SCORING, "validity": VALIDITY},
               "fields": {"scores": True, "validity": True}}
    document = json.loads(value) if value else default
    supported = [default["policies"], {"scoring": SCORING, "validity": LEGACY_VALIDITY}]
    if not isinstance(document, dict) or document.get("policies") not in supported:
        raise CatalystError("Unsupported Catalyst evaluation policies.")
    fields = document.get("fields")
    if (not isinstance(fields, dict) or set(fields) != {"scores", "validity"}
            or any(type(item) is not bool for item in fields.values())
            or not any(fields.values())):
        raise CatalystError("Invalid requested evaluation fields.")
    return {"policies": document["policies"], "fields": fields}


def bound_result(result: dict, request: dict, evaluation_id: str, *, original_request=True) -> None:
    expected = {
        "protocol": PROTOCOL, "evaluation_id": evaluation_id,
        "source_digest": request["source"]["digest"],
        "evaluation_config_digest": digest(request["evaluation"]),
        "problem_set_digest": digest(request["problem_set"]),
        "policies_digest": digest(request["judge"]["policies"]),
        "pricing_digest": digest(request["pricing"]),
    }
    if original_request:
        expected["request_id"] = request["request_id"]
    if "evidence_mode" in request:
        expected["evidence_mode"] = request["evidence_mode"]
    if (not isinstance(result, dict) or any(result.get(key) != value for key, value in expected.items())
            or result.get("status") not in PENDING | TERMINAL):
        raise CatalystError("Remote result does not match this evaluation request.")


def judgment(result: dict, request: dict) -> dict:
    """Project only trusted, bound observations into Yukon's public artifact."""
    judge = judge_input(json.dumps(request["judge"]))
    if result.get("status") != "completed":
        raise CatalystError("Remote evaluation did not complete; no score is published.")
    if (result.get("evidence_mode") in {"local-test", "local-ecdsa"}
            and request.get("evidence_mode") != result["evidence_mode"]):
        raise CatalystError("Local-test or local ECDSA evidence cannot be used as a hosted evaluation.")
    if type(result.get("valid")) is not bool or not isinstance(result.get("reason"), str):
        raise CatalystError("Remote evaluator omitted its validity judgment.")
    # This attests internal evidence retention, not a user download capability.
    if result.get("trace_available") is not True:
        raise CatalystError("Remote evaluator did not retain evaluation traces.")
    built = result.get("build")
    if (not isinstance(built, dict) or not isinstance(built.get("id"), str) or not built["id"]
            or not isinstance(built.get("image_digest"), str) or not IMAGE_RE.fullmatch(built["image_digest"])):
        raise CatalystError("Remote evaluator omitted the immutable build/image identity.")
    observations = result.get("observations")
    if not isinstance(observations, list):
        raise CatalystError("Remote evaluator omitted problem observations.")
    public, scores, seen = [], [], set()
    for observation in observations:
        if not isinstance(observation, dict):
            raise CatalystError("Malformed remote observation.")
        identity = observation.get("problem_id")
        problem = next((p for p in request["problem_set"] if p["id"] == identity), None)
        if (not problem or identity in seen
                or observation.get("problem_commit") != problem["repository"]["commit"]):
            raise CatalystError("Remote observation has a wrong or duplicate problem binding.")
        seen.add(identity)
        config = request["evaluation"]
        projected = project_observation(observation, evaluation_models(config), config["max_model_credits"],
                                        config["limits"], request["pricing"],
                                        allow_inflight_overshoot=judge["policies"]["validity"] == VALIDITY)
        public.append({"problem_id": identity, "problem_commit": observation["problem_commit"], **projected})
    if result["valid"]:
        if seen != {p["id"] for p in request["problem_set"]}:
            raise CatalystError("Valid evaluation must independently verify ecdsa.fail.")
        best = public[0]["best"]
        if best is None:
            raise CatalystError("Valid scored evaluation has no verified candidate.")
        # A finite two-value adapter for Yukon. Missing tier measurements stay
        # explicit in metadata, never padded with invented scores or sentinels.
        scores = [best["performance"], best["normalized_model_usd"]]
    elif not result["reason"].strip():
        raise CatalystError("Invalid evaluation requires an explanation.")
    fields = request["judge"]["fields"]
    artifact = {"metrics": {
        "evaluationId": result["evaluation_id"], "sourceDigest": request["source"]["digest"],
        "buildId": built["id"], "imageDigest": built["image_digest"],
        "model": request["evaluation"]["model"], "observations": public,
        "models": evaluation_models(request["evaluation"]),
        "problemSetDigest": digest(request["problem_set"]),
        "problemRelease": request["problem_set"][0].get("release"),
        "evaluationConfigDigest": digest(request["evaluation"]),
        "pricingDigest": digest(request["pricing"]),
        "maxModelCredits": request["evaluation"]["max_model_credits"],
        "limits": request["evaluation"]["limits"],
        "evidenceMode": result.get("evidence_mode", "remote"),
    }}
    if result.get("model_access") in {"disabled", "mock", "metered"}:
        artifact["metrics"]["modelAccess"] = result["model_access"]
    if "source_audit" in result:
        audit = result["source_audit"]
        required = {"policy", "digest", "config_digest", "model", "status"}
        if (not isinstance(audit, dict)
                or set(audit) != required
                or audit["digest"] != request["source"]["digest"]
                or audit["status"] != "passed"
                or any(not isinstance(audit[k], str) or not audit[k] for k in required)):
            raise CatalystError("Source audit does not match a passed review of this harness.")
        from .harness_summary import public_summary
        artifact["metrics"]["sourceAudit"] = {key: audit[key] for key in required}
        summary = public_summary(result.get("harness_summary"))
        if summary is not None:
            artifact["metrics"]["sourceAudit"]["summary"] = summary
    if fields["scores"]:
        artifact["scores"] = scores if result["valid"] else None
    if fields["validity"]:
        artifact.update(valid=result["valid"], reason=result["reason"][:2000])
    return artifact


def verification_reference(result: dict, body: dict) -> dict:
    return {
        "schema_version": 2, "evaluation_id": result["evaluation_id"],
        "source_digest": body["source"]["digest"],
        "evaluation_config_digest": digest(body["evaluation"]),
        "problem_set_digest": digest(body["problem_set"]),
        "policies_digest": digest(body["judge"]["policies"]),
        "pricing_digest": digest(body["pricing"]),
        "image_digest": result["build"]["image_digest"],
        "evidence_mode": body.get("evidence_mode", "remote"),
    }


def evaluation_id(value):
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise CatalystError("Expected a canonical evaluation UUID.") from None
    return value
