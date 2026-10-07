from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import sqlite3
import uuid

from .common import CatalystError, canonical, finite_number, now, open_bundle


class Catalog:
    """Immutable bundles are authoritative; SQLite indexes their metadata."""

    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS objects (
                    kind TEXT NOT NULL, id TEXT NOT NULL, version TEXT NOT NULL,
                    document TEXT NOT NULL, published_at TEXT NOT NULL,
                    PRIMARY KEY (kind, id, version)
                );
                CREATE INDEX IF NOT EXISTS objects_kind ON objects(kind);
                CREATE INDEX IF NOT EXISTS run_problem ON objects(
                    json_extract(document, '$.problem.id'),
                    json_extract(document, '$.problem.version')
                ) WHERE kind = 'run';
                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL, run_version TEXT NOT NULL,
                    body TEXT NOT NULL, supporting_run TEXT, created_at TEXT NOT NULL
                );
            """)

    def connect(self):
        db = sqlite3.connect(self.root / "catalog.sqlite", timeout=15)
        db.row_factory = sqlite3.Row
        return db

    def bundle_path(self, kind, identity, version):
        from .common import identifier, version_id, KINDS
        if kind not in KINDS:
            raise CatalystError("Unknown object kind.")
        return self.root / "objects" / kind / identifier(identity) / f"{version_id(version)}.zip"

    def publish(self, content: bytes):
        snapshot, _ = open_bundle(content)
        document = snapshot["document"]
        kind, identity, version = snapshot["kind"], snapshot["id"], snapshot["version"]
        with self.connect() as db:
            if kind == "run":
                existing = db.execute("SELECT version FROM objects WHERE kind='run' AND id=?", (identity,)).fetchone()
                if existing and existing["version"] != version:
                    raise CatalystError("Published run IDs are immutable. Create a new attempt instead.")
                if document["status"] in {"running", "planned", "prepared"}:
                    raise CatalystError("Wait until the attempt finishes before publishing it.")
                for key in ("problem", "harness"):
                    ref = document[key]
                    row = db.execute("SELECT document FROM objects WHERE kind=? AND id=? AND version=?",
                                     (key, ref["id"], ref["version"])).fetchone()
                    if row is None:
                        raise CatalystError(f"Publish the referenced {key} snapshot first.")
                    if key == "problem" and json.loads(row["document"])["metric"] != document["metric"]:
                        raise CatalystError("Run metric differs from the problem snapshot.")
            target = self.bundle_path(kind, identity, version)
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                temporary = target.with_name(f".{uuid.uuid4().hex}.tmp")
                temporary.write_bytes(content)
                temporary.replace(target)
            db.execute("INSERT OR IGNORE INTO objects VALUES (?, ?, ?, ?, ?)",
                       (kind, identity, version, canonical(document).decode(), now()))
        return {"kind": kind, "id": identity, "version": version}

    def get(self, kind, identity, version):
        self.bundle_path(kind, identity, version)  # Validate identifiers.
        with self.connect() as db:
            row = db.execute("SELECT * FROM objects WHERE kind=? AND id=? AND version=?",
                             (kind, identity, version)).fetchone()
        if row is None:
            raise CatalystError("Published snapshot not found.")
        return self._object(row)

    @staticmethod
    def _object(row):
        return {"kind": row["kind"], "id": row["id"], "version": row["version"],
                "published_at": row["published_at"], "document": json.loads(row["document"])}

    def list(self, kind=None):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM objects WHERE kind=? ORDER BY published_at DESC, id"
                              if kind else "SELECT * FROM objects ORDER BY published_at DESC, id",
                              (kind,) if kind else ()).fetchall()
        return [self._object(row) for row in rows]

    def matrix(self, problem_id, problem_version, budget, model=None, conditions=None):
        budget = finite_number(budget, nonnegative=True) if budget is not None else None
        problem = self.get("problem", problem_id, problem_version)
        with self.connect() as db:
            rows = db.execute("""
                SELECT * FROM objects WHERE kind='run'
                AND json_extract(document, '$.problem.id')=?
                AND json_extract(document, '$.problem.version')=?
                ORDER BY published_at, id
            """, (problem_id, problem_version)).fetchall()
            reports = db.execute("SELECT run_id,run_version,COUNT(*) AS n FROM reports GROUP BY run_id,run_version").fetchall()
        report_counts = {(r["run_id"], r["run_version"]): r["n"] for r in reports}
        runs = [self._object(row) for row in rows]
        seen = set()
        unique = []
        for run in runs:
            key = run["document"].get("source_record_sha256") or run["id"]
            if key not in seen:
                unique.append(run)
                seen.add(key)
        runs = unique
        models = sorted({r["document"]["model"] for r in runs})
        model = model if model in models else (models[0] if model is None and models else None)
        filtered = [r for r in runs if r["document"]["model"] == model]
        condition_labels = {r["document"]["conditions"]: r["document"].get("condition_label", "")
                            for r in filtered}
        condition_ids = sorted(condition_labels)
        conditions = conditions if conditions in condition_ids else (
            condition_ids[0] if conditions is None and condition_ids else None)
        filtered = [r for r in filtered if r["document"]["conditions"] == conditions]
        groups = defaultdict(list)
        for run in filtered:
            doc = run["document"]
            groups[(doc["harness"]["id"], doc["harness"]["version"])].append(run)
        direction = problem["document"]["metric"]["direction"]
        choose = min if direction == "minimize" else max
        entries = []
        for (identity, version), attempts in groups.items():
            harness = self.get("harness", identity, version)["document"]
            samples, views = [], []
            for attempt in attempts:
                doc = attempt["document"]
                usable = [p for p in doc["observations"] if budget is None or p["cost"] <= budget]
                best = None
                if usable and doc.get("cost_known", True):
                    score = choose(p["score"] for p in usable)
                    best = min((p for p in usable if p["score"] == score), key=lambda p: p["cost"])
                    samples.append(best)
                views.append({**attempt, "within_budget": best,
                              "report_count": report_counts.get((attempt["id"], attempt["version"]), 0)})
            best_sample = choose(samples, key=lambda p: p["score"]) if samples else None
            if best_sample:
                best_sample = min((p for p in samples if p["score"] == best_sample["score"]),
                                  key=lambda p: p["cost"])
            entries.append({
                "id": identity, "version": version, "title": harness["title"],
                "score": best_sample["score"] if best_sample else None,
                "cost": best_sample["cost"] if best_sample else None,
                "range": [min(p["score"] for p in samples), max(p["score"] for p in samples)] if samples else None,
                "sample_count": len(samples), "attempt_count": len(attempts),
                "frontier": False, "runs": views,
            })
        eligible = [e for e in entries if e["score"] is not None]
        for entry in eligible:
            def dominates(other):
                better = other["score"] <= entry["score"] if direction == "minimize" else other["score"] >= entry["score"]
                strict = other["score"] != entry["score"] or other["cost"] < entry["cost"]
                return better and other["cost"] <= entry["cost"] and strict
            entry["frontier"] = not any(dominates(other) for other in eligible if other is not entry)
        entries.sort(key=lambda e: (
            e["score"] is None,
            (e["score"] if direction == "minimize" else -e["score"]) if e["score"] is not None else 0,
            e["cost"] if e["cost"] is not None else float("inf"), -e["sample_count"], e["id"]))
        return {
            "problem": problem, "budget": budget, "model": model, "models": models,
            "conditions": conditions,
            "condition_options": [{"id": key, "label": condition_labels[key]} for key in condition_ids],
            "entries": entries,
            "cost_label": "Model credits, including known continuation ancestors; infrastructure excluded",
            "ranking": "Best reported result in the selected comparison; all attempts retained. "
                       "Local records are illustrative and do not establish trusted checkpoint eligibility.",
        }

    def report(self, run_id, run_version, body, supporting_run=None):
        self.get("run", run_id, run_version)
        if not isinstance(body, str) or not body.strip() or len(body) > 10000:
            raise CatalystError("A report needs 1–10,000 characters of explanation.")
        if supporting_run is not None and not isinstance(supporting_run, str):
            raise CatalystError("Supporting run must be a reference.")
        identity = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("INSERT INTO reports VALUES (?, ?, ?, ?, ?, ?)",
                       (identity, run_id, run_version, body.strip(), supporting_run, now()))
        return {"id": identity, "status": "reported concern; no automatic finding of overfitting"}

    def reports(self, run_id, run_version):
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM reports WHERE run_id=? AND run_version=? ORDER BY created_at",
                (run_id, run_version))]
