"""Credit accounting and checkpoint projection for trusted evaluator results.

These validators check a server-owned record; they do not attest client records
or implement worker isolation, model authorization, or checkpoint collection.
"""
from __future__ import annotations

from decimal import Decimal
import hashlib
from pathlib import Path

from .common import CatalystError, canonical, finite_number, read_json, version_id

TIERS = (20, 200)
SCORING = {"version": "ecdsa-best-and-checkpoints-v2"}
VALIDITY = {"version": "ecdsa-trusted-checkpoints-v2"}


def tier(value) -> int:
    if type(value) is not int or value not in TIERS:
        raise CatalystError("budget_tier must be 20 or 200 model credits.")
    return value


def pricing_schedule() -> dict:
    return read_json(Path(__file__).parent / "problem-set/pricing.json")


def pricing_digest() -> str:
    return hashlib.sha256(canonical(pricing_schedule())).hexdigest()


def model_prices(model: dict) -> dict:
    for entry in pricing_schedule()["entries"]:
        if entry["provider"] == model.get("provider") and model.get("name") in entry["request_models"]:
            return entry
    raise CatalystError("Provider/model is absent from the pinned credit pricing schedule.")


def integer(value, label, minimum=0) -> int:
    if type(value) is not int or value < minimum:
        raise CatalystError(f"{label} must be an integer >= {minimum}.")
    return value


def credits(usage: dict, model: dict) -> Decimal:
    """Price inclusive input/output counts; cache buckets are input subsets."""
    keys = {"input_tokens", "output_tokens", "cached_read_tokens", "cache_write_tokens"}
    if not isinstance(usage, dict) or set(usage) != keys:
        raise CatalystError("Usage requires input, output, cache-read and cache-write token counts.")
    counts = {key: integer(usage[key], key) for key in keys}
    uncached = counts["input_tokens"] - counts["cached_read_tokens"] - counts["cache_write_tokens"]
    if uncached < 0:
        raise CatalystError("Cached token counts exceed inclusive input tokens.")
    prices = model_prices(model)
    long_context = prices.get("long_context")
    if long_context and counts["input_tokens"] > long_context["threshold_input_tokens"]:
        prices = long_context
    total = Decimal(0)
    for count, rate in (
        (uncached, "input_per_mtok"), (counts["output_tokens"], "output_per_mtok"),
        (counts["cached_read_tokens"], "cached_read_per_mtok"),
        (counts["cache_write_tokens"], "cache_write_per_mtok"),
    ):
        if count and rate not in prices:
            raise CatalystError(f"Unpriced token bucket: {rate}.")
        total += count * Decimal(str(prices.get(rate, 0)))
    return total / Decimal(1_000_000)


def amount(value) -> Decimal:
    finite_number(value, nonnegative=True)
    return Decimal(str(value))


def credit_limit(value) -> Decimal:
    limit = amount(value)
    if limit <= 0:
        raise CatalystError("max_model_credits must be positive.")
    return limit


def project_observation(observation: dict, model: dict, max_model_credits, limits: dict) -> dict:
    """Recompute costs, bind snapshots to settled usage and close tier windows.

    The runner assigns one sequence across usage, captures and checkpoint seals.
    Verification can complete later, but must judge the exact captured digest.
    """
    funded_limit = credit_limit(max_model_credits)
    if observation.get("pricing_digest") != pricing_digest():
        raise CatalystError("Observation uses a different pricing schedule.")
    end = integer(observation.get("end_sequence"), "end_sequence", 1)
    seen = set()

    def sequence(value):
        value = integer(value, "sequence", 1)
        if value > end or value in seen:
            raise CatalystError("Duplicate sequence or event after evaluation end.")
        seen.add(value)
        return value

    ledger = observation.get("usage")
    if not isinstance(ledger, list):
        raise CatalystError("Observation requires a complete trusted usage ledger.")
    charges, previous, total, tokens = [], 0, Decimal(0), 0
    requests = set()
    for event in ledger:
        if not isinstance(event, dict):
            raise CatalystError("Malformed usage event.")
        seq = sequence(event.get("sequence"))
        request_id = event.get("request_id")
        if (seq <= previous or not isinstance(request_id, str) or not request_id
                or request_id in requests or event.get("settled") is not True):
            raise CatalystError("Usage must be ordered, uniquely identified and settled.")
        previous = seq
        requests.add(request_id)
        total += credits(event.get("tokens"), model)
        tokens += event["tokens"]["input_tokens"] + event["tokens"]["output_tokens"]
        charges.append((seq, total))
    if tokens > limits["max_model_tokens"]:
        raise CatalystError("Remote usage exceeded the authorized token limit.")
    if total != amount(observation.get("normalized_model_usd")) or total > funded_limit:
        raise CatalystError("Remote usage disagrees with pricing or exceeds the authorized credit limit.")

    def cost_before(seq):
        return next((cost for position, cost in reversed(charges) if position < seq), Decimal(0))

    checkpoints = observation.get("checkpoints")
    if not isinstance(checkpoints, list):
        raise CatalystError("Observation requires trusted checkpoint seals.")
    seals, last_seq, last_tier = {}, 0, 0
    for checkpoint in checkpoints:
        if not isinstance(checkpoint, dict):
            raise CatalystError("Malformed checkpoint seal.")
        budget = tier(checkpoint.get("budget_tier"))
        seq = sequence(checkpoint.get("sequence"))
        if (budget > funded_limit or budget <= last_tier or seq <= last_seq
                or checkpoint.get("settled") is not True or cost_before(seq) > budget):
            raise CatalystError("Invalid checkpoint order, funding or settled usage.")
        seals[budget] = seq
        last_seq, last_tier = seq, budget
    curve = observation.get("curve")
    if not isinstance(curve, list):
        raise CatalystError("Observation requires the complete verified performance/cost curve.")
    points, previous = [], 0
    for point in curve:
        if not isinstance(point, dict):
            raise CatalystError("Malformed candidate point.")
        seq = sequence(point.get("captured_sequence"))
        candidate = version_id(point.get("candidate_digest"))
        if (seq <= previous or point.get("settled") is not True
                or point.get("verified") is not True
                or point.get("verified_candidate_digest") != candidate):
            raise CatalystError("Candidate is unordered, unsettled or not independently verified.")
        previous = seq
        cost = cost_before(seq)
        if cost != amount(point.get("normalized_model_usd")):
            raise CatalystError("Candidate cost is not its cumulative trusted usage at capture.")
        toffoli = finite_number(point.get("avg_toffoli"), nonnegative=True)
        qubits = integer(point.get("peak_qubits"), "peak_qubits", 1)
        performance = finite_number(point.get("performance"), nonnegative=True)
        if toffoli <= 0 or performance != finite_number(toffoli * qubits):
            raise CatalystError("ECDSA performance must equal avg_toffoli * peak_qubits.")
        points.append({
            "candidate_digest": candidate, "captured_sequence": seq,
            "normalized_model_usd": float(cost), "performance": performance,
            "avg_toffoli": toffoli, "peak_qubits": qubits,
        })
    summaries = []
    for budget in TIERS:
        eligible = [p for p in points if budget in seals
                    and p["captured_sequence"] < seals[budget]
                    and amount(p["normalized_model_usd"]) <= budget]
        best = min(eligible, key=lambda p: (p["performance"], p["normalized_model_usd"],
                                           p["captured_sequence"]), default=None)
        status = ("not_funded" if budget > funded_limit else "not_evaluated" if budget not in seals
                  else "eligible" if best else "no_verified_candidate")
        summaries.append({"budget_tier": budget, "status": status, "best": best})
    best = min(points, key=lambda p: (p["performance"], p["normalized_model_usd"],
                                      p["captured_sequence"]), default=None)
    return {"normalized_model_usd": float(total), "pricing_digest": pricing_digest(),
            "curve": points, "tiers": summaries, "best": best,
            "checkpoints": [{"budget_tier": budget, "sequence": seq} for budget, seq in seals.items()]}
