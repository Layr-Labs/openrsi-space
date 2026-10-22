#!/usr/bin/env python3
"""Eval sidecar for ecdsa-fail: the agent's `evaluate` feedback service.

Runs the SAME scoring core as the one-shot verifier (grade.score_candidate) --
compile the candidate `point_add.rs` into the trusted crate and run the
un-gameable Fiat-Shamir benchmark -- but as a metered HTTP service the agent
submits to. Because the benchmark derives its test points from the candidate's
own op stream, there is nothing to hide: the returned score IS the real
objective, the same one the verifier reports. So (unlike world-map's dev-scorer)
there is no dev/holdout split; metering bounds compute, not information.

Each submission is a full build + heavy simulation (~15 GB, tens of seconds), so
requests are serialized and capped by a submission budget.
"""

from __future__ import annotations

from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import grade

PORT = int(os.environ.get("DEV_SCORER_PORT", "8090"))
MAX_SUBMISSIONS = int(os.environ.get("MAX_SUBMISSIONS", "200"))
MAX_SOURCE_BYTES = int(os.environ.get("MAX_SOURCE_BYTES", str(4 * 1024 * 1024)))
RUN_ID = os.environ.get("TESTBED_RUN_ID", "unknown")
USAGE_DIR = Path(os.environ.get("TESTBED_USAGE_DIR", "/var/lib/testbed/usage"))
EVENT_TOKEN_FILENAME = ".event-token"
DEFAULT_EVENT_URL = "http://gateway:8080/internal/events"

NOTE = (
    "real objective (avg_Toffoli x peak_qubits, lower is better); the verifier "
    "re-runs this same benchmark for the reported score"
)

_lock = threading.Lock()
_submissions = 0
_best_score: float | None = None  # minimize, so best = smallest seen


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _append_jsonl_locked(path: Path, record: dict) -> None:
    encoded = json.dumps(record, sort_keys=True, separators=(",", ":"))
    with path.open("a+", encoding="utf-8") as output:
        try:
            path.chmod(0o666)
        except OSError:
            pass
        fcntl.flock(output.fileno(), fcntl.LOCK_EX)
        try:
            event_id = record.get("event_id")
            if event_id:
                event_needle = '"event_id":' + json.dumps(event_id)
                source_needle = (
                    '"source":' + json.dumps(record.get("source"))
                )
                output.seek(0)
                for line in output:
                    if event_needle in line and source_needle in line:
                        return
            output.seek(0, os.SEEK_END)
            output.write(encoded + "\n")
            output.flush()
        finally:
            fcntl.flock(output.fileno(), fcntl.LOCK_UN)


def _emit_usage_event(kind: str, data: dict, event_id: str) -> None:
    observed_at = _utc_now()
    document = {
        "run_id": RUN_ID,
        "source": "evaluator",
        "kind": kind,
        "observed_at": observed_at,
        "event_id": event_id,
        "data": data,
    }
    try:
        token = (USAGE_DIR / EVENT_TOKEN_FILENAME).read_text(
            encoding="utf-8"
        ).strip()
        if not token:
            raise OSError("empty gateway event token")
        request = urllib.request.Request(
            os.environ.get("DUNGENESS_EVENT_URL", DEFAULT_EVENT_URL),
            data=json.dumps(document, separators=(",", ":")).encode("utf-8"),
            headers={
                "content-type": "application/json",
                "x-dungeness-event-token": token,
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=2):
            return
    except (OSError, urllib.error.URLError, TypeError, ValueError):
        pass

    record = {
        "schema_version": 1,
        "run_id": RUN_ID,
        "sequence": None,
        "source": "evaluator",
        "kind": kind,
        "observed_at": observed_at,
        "recorded_at": _utc_now(),
        "event_id": event_id,
        "data": data,
    }
    if kind == "evaluation.completed":
        try:
            summary = json.loads(
                (USAGE_DIR / "summary.json").read_text(encoding="utf-8")
            )
            usage = summary.get("usage") if isinstance(summary, dict) else None
            if isinstance(usage, dict):
                record["usage"] = usage
        except (OSError, json.JSONDecodeError):
            pass
    try:
        USAGE_DIR.mkdir(parents=True, exist_ok=True)
        _append_jsonl_locked(USAGE_DIR / "events.jsonl", record)
    except OSError:
        pass


def _record(event: dict) -> None:
    """Append one submission event to the canonical run log (best-effort)."""
    payload = dict(event)
    event_id = str(payload.pop("event_id", f"evaluation:{time.time_ns()}"))
    payload.update(
        {
            "submissions_used": _submissions,
            "submissions_limit": MAX_SUBMISSIONS,
            "best_score": _best_score,
        }
    )
    try:
        USAGE_DIR.mkdir(parents=True, exist_ok=True)
        _emit_usage_event(
            "evaluation.completed",
            payload,
            event_id,
        )
    except OSError:
        pass


class Handler(BaseHTTPRequestHandler):
    def _reply(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/healthz":
            self._reply(200, {"status": "ok"})
        elif self.path == "/status":
            with _lock:
                self._reply(
                    200,
                    {
                        "submissions_used": _submissions,
                        "submissions_limit": MAX_SUBMISSIONS,
                        "submissions_remaining": max(
                            0,
                            MAX_SUBMISSIONS - _submissions,
                        ),
                        "best_score": _best_score,
                    },
                )
        else:
            self._reply(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        global _submissions, _best_score
        if self.path != "/score":
            self._reply(404, {"error": "not found"})
            return
        length = int(self.headers.get("content-length", "0"))
        if length <= 0 or length > MAX_SOURCE_BYTES:
            self._reply(400, {"error": "missing or oversized candidate"})
            return
        source = self.rfile.read(length)
        digest = hashlib.sha256(source).hexdigest()
        started = time.monotonic()
        # Serialize: one submission at a time (heavy build+sim, shared workdir),
        # and meter the budget so probing cannot be unbounded.
        with _lock:
            if _submissions >= MAX_SUBMISSIONS:
                event_id = f"evaluation:budget:{time.time_ns()}"
                _record({
                    "event_id": event_id,
                    "operation": "score",
                    "status": "budget_rejected",
                    "source_sha256": digest,
                })
                self._reply(429, {"error": "submission budget exhausted"})
                return
            _submissions += 1
            submission_index = _submissions
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    src = Path(tmp) / "point_add.rs"
                    src.write_bytes(source)
                    details = grade.score_candidate(src)
            except ValueError as error:
                _submissions -= 1  # malformed input: refund, nothing was run
                self._reply(400, {"error": str(error)})
                return
            except Exception:  # noqa: BLE001 - never leak internals to the agent
                event_id = f"evaluation:{submission_index}"
                _record({
                    "event_id": event_id,
                    "operation": "score",
                    "status": "error",
                    "source_sha256": digest,
                })
                self._reply(500, {"error": "scoring failed"})
                return

            status = details["status"]
            score = details["score"]
            if status == "ok" and (_best_score is None or score < _best_score):
                _best_score = score
            event_id = f"evaluation:{submission_index}"
            _record({
                "event_id": event_id,
                "operation": "score",
                "status": status,
                "score": score,
                "avg_toffoli": details["avg_toffoli"],
                "peak_qubits": details["peak_qubits"],
                "submissions_remaining": MAX_SUBMISSIONS - _submissions,
                "duration_ms": round((time.monotonic() - started) * 1000),
                "source_sha256": digest,
                "candidate_sha256": digest,
            })

        payload = {
            "status": status,
            "score": score,
            "avg_toffoli": details["avg_toffoli"],
            "peak_qubits": details["peak_qubits"],
            "submissions_remaining": MAX_SUBMISSIONS - _submissions,
            "note": NOTE,
            "candidate_sha256": digest,
        }
        # When the build/correctness checks fail, hand back the tail of the
        # compiler/harness output: it is the agent's OWN code failing, and the
        # benchmark leaks no answers, so this is legitimate debugging feedback.
        if status != "ok":
            payload["detail"] = (details.get("stderr_tail") or "")[-2000:]
        self._reply(200, payload)

    def log_message(self, *args) -> None:  # silence request logging
        pass


if __name__ == "__main__":
    if not grade.EVALUATOR_ROOT.is_dir():
        raise SystemExit(f"eval sidecar: evaluator missing: {grade.EVALUATOR_ROOT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
