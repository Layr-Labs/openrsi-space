"""Safe human-readable progress; live observations never become score evidence."""
from __future__ import annotations

import math
import re

DIAGNOSTIC_MESSAGES = {
    "MODEL_USAGE_UNAVAILABLE": "A model request has no trusted usage; total credits are incomplete. Operator investigation is needed before a verified receipt can be issued.",
    "WORKER_FAILED": "The worker failed; the available evidence does not establish the cause.",
    "upstream_read_timeout": "The gateway timed out waiting for upstream response data.",
    "upstream_connect_timeout": "The gateway timed out connecting upstream.",
    "upstream_transport_timeout": "An upstream transport operation timed out.",
    "upstream_protocol_error": "The gateway observed an upstream HTTP protocol failure.",
    "upstream_connection_error": "The gateway observed an upstream connection failure.",
    "gateway_cancelled": "The gateway's upstream request task was cancelled.",
    "transport_failure_unknown": "The transport failure was not classified; its origin is undetermined.",
    "HARNESS_EXIT_NONZERO": "Harness exited unsuccessfully; inspect its reported error and local recovery tests.",
    "HARNESS_TIMEOUT": "Harness execution reached the runtime timeout.",
    "RUNTIME_ERROR": "Runtime failed; contact the operator if local harness checks pass.",
    "CANDIDATE_REJECTED": "Candidate failed independent verification; use the assigned evaluator during development.",
    "EVALUATION_TIMEOUT": "Candidate evaluation timed out.",
    "EVALUATOR_ERROR": "Evaluator reported an error.",
    "EVALUATOR_RESULT_UNREADABLE": "Evaluator result could not be interpreted.",
    "EVALUATION_LIMIT_REACHED": "Candidate evaluation allowance was exhausted.",
    "EVALUATION_INTERRUPTED": "Candidate evaluation was interrupted.",
    "EVALUATION_STARTED": "Candidate evaluation started.",
    "EVALUATION_PASSED": "Candidate evaluation passed.",
}


def diagnostic_lines(result):
    report = result.get("diagnostics")
    if not isinstance(report, dict) or report.get("protocol") != "catalyst-diagnostics-v1":
        return []
    lines = []
    for section in ("worker", "runtime", "verification"):
        entry = report.get(section)
        if not isinstance(entry, dict):
            continue
        code = entry.get("code")
        if isinstance(code, str) and code in DIAGNOSTIC_MESSAGES:
            lines.append(f"{code}: {DIAGNOSTIC_MESSAGES[code]}")
        if section == "runtime":
            reported = entry.get("reported")
            if isinstance(reported, dict):
                exception = reported.get("exception_type")
                if isinstance(exception, str) and exception in {
                    "FileExistsError", "FileNotFoundError", "PermissionError", "TimeoutError",
                    "ValueError", "TypeError", "KeyError", "RuntimeError", "OSError", "MemoryError",
                    "JSONDecodeError", "ContractError", "CalledProcessError", "TimeoutExpired",
                }:
                    lines.append(f"Harness-reported exception: {exception}.")
    failures = report.get("model_failures")
    events = failures.get("events") if isinstance(failures, dict) else None
    if isinstance(events, list) and events and isinstance(events[-1], dict):
        event = events[-1]
        if event.get("code") == "MODEL_USAGE_UNAVAILABLE":
            message = f"MODEL_USAGE_UNAVAILABLE: {DIAGNOSTIC_MESSAGES['MODEL_USAGE_UNAVAILABLE']}"
            if message not in lines:
                lines.append(message)
            category = event.get("category")
            if isinstance(category, str) and category in DIAGNOSTIC_MESSAGES:
                lines.append(DIAGNOSTIC_MESSAGES[category])
            if event.get("request_status") == "stream_interrupted":
                lines.append("The model stream was interrupted. Later requests do not settle its missing usage.")
    if lines:
        identity = report.get("evaluation_id")
        if isinstance(identity, str) and re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", identity):
            lines.append(f"Read the owner report with catalyst remote diagnostics {identity}.")
    return lines


def number(value):
    if type(value) not in (int, float):
        return None
    try:
        return value if math.isfinite(value) and value >= 0 else None
    except OverflowError:
        return None


def duration(value):
    seconds = int(number(value) or 0)
    minutes, seconds = divmod(seconds, 60)
    return f"{minutes}m {seconds:02d}s"


def progress_line(result, waited_seconds=0):
    status = result.get("status")
    if status not in {"queued", "awaiting_credentials", "building", "running", "verifying",
                      "completed", "failed", "cancelled"}:
        status = "unknown"
    parts = [f"Remote status: {status}"]
    progress = result.get("progress")
    if not isinstance(progress, dict) or progress.get("schema_version") != 1:
        if waited_seconds >= 15:
            parts.append(f"waiting {duration(waited_seconds)}; no live metrics available")
        return " | ".join(parts)
    elapsed = number(progress.get("elapsed_seconds"))
    if elapsed is not None:
        parts.append(f"elapsed {duration(elapsed)}")
    usage = progress.get("usage")
    if isinstance(usage, dict):
        cost = number(usage.get("normalized_model_credits"))
        cap = number(progress.get("max_model_credits"))
        if cost is not None:
            parts.append(f"${cost:.6f}" + (f" / ${cap:g}" if cap is not None else "") + " credits")
        requests = number(usage.get("model_requests"))
        if requests is not None:
            parts.append(f"{int(requests)} model requests")
    else:
        parts.append("waiting for gateway usage")
    evaluation = progress.get("evaluation")
    if isinstance(evaluation, dict):
        count = number(evaluation.get("completed"))
        if count is not None:
            parts.append(f"{int(count)} evaluations")
        best = number(evaluation.get("best_performance"))
        if best is not None:
            parts.append(f"best {best:,.6f}".rstrip("0").rstrip(".") + " (provisional)")
    age = number(progress.get("snapshot_age_seconds"))
    if age is not None and age >= 30:
        parts.append(f"last metrics {duration(age)} ago")
    report = result.get("diagnostics")
    evaluations = (report.get("evaluations") if isinstance(report, dict)
                   and report.get("protocol") == "catalyst-diagnostics-v1" else None)
    events = evaluations.get("events") if isinstance(evaluations, dict) else None
    if isinstance(events, list) and events and isinstance(events[-1], dict):
        code = events[-1].get("code")
        if isinstance(code, str) and code in DIAGNOSTIC_MESSAGES:
            parts.append(f"latest evaluation: {code}")
    return " | ".join(parts)
