"""Adapt existing trusted Dungeness ECDSA results to Catalyst's score–cost curve.

Only the worker's retained gateway/evaluator log is accepted here. Submission
logs, solver timestamps and solver-provided scores are never inputs.
"""
from __future__ import annotations

from decimal import Decimal
import json

from .common import CatalystError, version_id
from .tiers import amount, credits, integer, usage_model


def project_history(run_dir, ledger, final_points, model, schedule=None):
    events = []
    previous = 0
    omitted = 0
    for line in (run_dir / "usage/events.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        sequence = event.get("sequence")
        if sequence is None:
            # Sidecar delivery fallback has no canonical gateway ordering.
            # Its snapshot cannot establish which charges preceded this result.
            if event.get("source") == "evaluator" and event.get("kind") == "evaluation.completed":
                omitted += 1
                continue
            raise CatalystError("Dungeness history contains an unordered event.")
        integer(sequence, "gateway sequence", 1)
        if sequence <= previous:
            raise CatalystError("Dungeness history must be in canonical gateway order.")
        previous = sequence
        events.append(event)

    accounting = {}
    starts = []
    rounded = Decimal(0)
    snapshots = {}
    for event in events:
        if event.get("source") == "gateway" and event.get("kind") == "model.accounting":
            request = event.get("request_id")
            if not request or request in accounting:
                raise CatalystError("Duplicate or unidentified gateway accounting.")
            accounting[request] = event["sequence"]
            data = event["data"]
            rounded += amount(data.get("normalized_usd", data.get("usd")))
        if event.get("source") == "gateway" and event.get("kind") == "model.request":
            request = event.get("request_id")
            if not request:
                raise CatalystError("Unidentified gateway model request.")
            starts.append((event["sequence"], request))
        snapshots[event["sequence"]] = rounded

    ordered = []
    for entry in ledger:
        sequence = accounting.get(entry["request_id"])
        if sequence is None:
            raise CatalystError("Settled usage is missing its gateway event.")
        ordered.append((sequence, 0, dict(entry)))
    for event in events:
        if event.get("source") != "evaluator" or event.get("kind") != "evaluation.completed":
            continue
        data = event.get("data", {})
        if data.get("operation") != "score" or data.get("status") != "ok":
            continue
        sequence = event["sequence"]
        if abs(amount(event.get("usage", {}).get("normalized_usd")) - snapshots[sequence]) > Decimal("0.00000001"):
            raise CatalystError("Evaluator usage snapshot disagrees with Dungeness accounting.")
        # A streaming request must not make a result look cheaper while its
        # accounting is pending. Charge it when settled, conservatively including
        # any other charges that settled in that interval.
        pending = [request for start, request in starts if start < sequence]
        if any(request not in accounting for request in pending):
            raise CatalystError("Evaluator result has an unsettled model request.")
        settled = max([sequence, *(accounting[request] for request in pending)])
        digest = version_id(data.get("candidate_sha256"))
        point = {
            "candidate_digest": digest, "verified_candidate_digest": digest,
            "candidate_digest_kind": "dungeness-ecdsa-module-sha256-v1",
            "source_digest": version_id(data.get("source_sha256")),
            "verification_source": "dungeness-evaluator",
            "gateway_sequence": sequence,
            "verified": True, "settled": True,
            "avg_toffoli": data.get("avg_toffoli"), "peak_qubits": data.get("peak_qubits"),
            "performance": data.get("score"),
        }
        ordered.append((settled, sequence, point))
    for index, point in enumerate(final_points):
        ordered.append((previous + 1, index + 1, {**point, "verification_source": "terminal-verifier",
                                                 "candidate_digest_kind": "catalyst-files-sha256-v1"}))
    ordered.sort(key=lambda entry: (entry[0], entry[1]))
    result_ledger, curve, cost = [], [], Decimal(0)
    for sequence, (_, kind, item) in enumerate(ordered, 1):
        if kind == 0:
            cost += credits(item["tokens"], usage_model(item, model), schedule)
            item["sequence"] = sequence
            result_ledger.append(item)
        else:
            item["captured_sequence"] = sequence
            item["normalized_model_usd"] = float(cost)
            curve.append(item)
    return result_ledger, curve, len(ordered) + 1, omitted
