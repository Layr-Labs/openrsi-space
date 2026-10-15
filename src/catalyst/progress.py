"""Safe human-readable progress; live observations never become score evidence."""
from __future__ import annotations

import math


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
    return " | ".join(parts)
