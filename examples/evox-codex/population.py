"""Evaluated candidate archive; scores come only from the assigned evaluator."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from snapshots import candidate_path, copy_candidate, locked


def read(state):
    path = state / "population.json"
    return json.loads(path.read_text()) if path.exists() else {"direction": None, "candidates": [], "attempts": []}


def save(state, data):
    pending = state / "population.pending.json"
    pending.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    pending.replace(state / "population.json")


def fingerprint(path):
    h = hashlib.sha256()
    paths = sorted(path.rglob("*")) if path.is_dir() else [path]
    for item in paths:
        if item.is_file():
            name = str(item.relative_to(path)) if path.is_dir() else item.name
            raw = item.read_bytes()
            h.update(json.dumps([name, len(raw)]).encode() + b"\0" + raw)
    return h.hexdigest()


def best(data):
    if not data["candidates"]:
        return None
    return sorted(data["candidates"], key=lambda c: c["score"], reverse=data["direction"] == "maximize")[0]


def check(task, state, direction, note="", timeout=240):
    with locked(state):
        data = read(state)
        if direction not in {"minimize", "maximize"} or data["direction"] not in {None, direction}:
            raise ValueError("Objective direction must remain fixed.")
        data["direction"] = direction
        target = candidate_path(task)
        folder = Path(tempfile.mkdtemp(prefix="candidate-", dir=state))
        snapshot = folder / target.name
        retained = False
        try:
            copy_candidate(target, snapshot)
            digest = fingerprint(snapshot)
            for candidate in data["candidates"]:
                if candidate["digest"] == digest:
                    return {"duplicate": True, "candidate": candidate, "best_score": best(data)["score"]}
            try:
                proc = subprocess.run(["evaluate", "--json", str(snapshot)], capture_output=True,
                                      text=True, timeout=timeout)
                result = json.loads(proc.stdout)
                if not isinstance(result, dict):
                    raise ValueError("Non-object evaluator response")
                score = result.get("score")
                valid = (proc.returncode == 0 and result.get("status") == "ok" and result.get("valid") is not False
                         and type(score) in (int, float) and math.isfinite(score))
            except (ValueError, OSError, subprocess.TimeoutExpired) as error:
                result, valid, score = {"status": "error", "message": str(error)[:2000]}, False, None
            # Ensure malformed non-finite verifier values cannot corrupt the archive.
            result = json.loads(json.dumps(result), parse_constant=lambda _: None)
            previous = best(data)
            attempt = {"digest": digest, "valid": valid, "note": note[:2000], "result": result,
                       "time": time.time(), "parent": os.environ.get("EVOX_PARENT", "none")}
            data["attempts"].append(attempt)
            if valid:
                data["candidates"].append({"id": digest[:16], "digest": digest, "score": score,
                    "snapshot": str(snapshot), "note": note[:2000], "selections": 0})
                retained = True
            current = best(data)
            save(state, data)
            return {"valid": valid, "result": result,
                    "improved": bool(current and (not previous or current["id"] != previous["id"])),
                    "best_score": current["score"] if current else None}
        finally:
            if not retained:
                shutil.rmtree(folder)


def restore(task, state, identity=None):
    with locked(state):
        data = read(state)
        candidate = best(data) if identity is None else next(c for c in data["candidates"] if c["id"] == identity)
        if candidate is None:
            return {"restored": False}
        source = Path(candidate["snapshot"])
        if not source.resolve().is_relative_to(state.resolve()):
            raise ValueError("Snapshot outside research state")
        target = candidate_path(task)
        with tempfile.TemporaryDirectory(prefix="restore-", dir=state) as temporary:
            staged = Path(temporary) / target.name
            copy_candidate(source, staged)
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(staged), str(target))
        return {"restored": True, "score": candidate["score"], "id": candidate["id"]}


def select(state, strategy):
    with locked(state):
        data = read(state)
        pool = sorted(data["candidates"], key=lambda c: c["score"], reverse=data["direction"] == "maximize")
        if not pool:
            return None, []
        if strategy["parent_rule"] == "best":
            parent = pool[0]
        elif strategy["parent_rule"] == "least_used":
            parent = min(pool, key=lambda c: c["selections"])
        else:
            # Cycle through score tiers to expose alternative approaches.
            parent = pool[sum(c["selections"] for c in pool) % len(pool)]
        parent["selections"] += 1
        others = [c for c in pool if c["id"] != parent["id"]]
        inspirations = others[:strategy["inspirations"]]
        save(state, data)
        return parent, inspirations


def describe(data):
    scores = sorted(c["score"] for c in data["candidates"])
    return {"direction": data["direction"], "valid_candidates": len(scores),
            "attempt_count": len(data["attempts"]), "recent_attempts": data["attempts"][-6:],
            "best_score": best(data)["score"] if scores else None,
            "score_range": [scores[0], scores[-1]] if scores else [],
            "median_score": scores[len(scores) // 2] if scores else None,
            "population": data["candidates"][-20:]}


def validate_strategy(value, direction=None):
    if not isinstance(value, dict) or set(value) != {"parent_rule", "operator", "inspirations", "direction", "rationale", "instructions"}:
        raise ValueError("Invalid strategy fields")
    if value["parent_rule"] not in {"best", "diverse", "least_used"} or value["operator"] not in {"refine", "restructure", "free"}:
        raise ValueError("Unsupported search policy")
    if type(value["inspirations"]) is not int or not 0 <= value["inspirations"] <= 3:
        raise ValueError("Invalid inspiration count")
    if value["direction"] not in {"minimize", "maximize"} or direction not in {None, value["direction"]}:
        raise ValueError("Invalid objective direction")
    if any(not isinstance(value[k], str) or not 1 <= len(value[k]) <= 6000 for k in ("rationale", "instructions")):
        raise ValueError("Invalid strategy instructions")
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["check", "restore", "status"])
    parser.add_argument("--direction", choices=["minimize", "maximize"])
    parser.add_argument("--note", default="")
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()
    task = json.loads(Path(os.environ["CATALYST_TASK"]).read_text())
    state = Path(os.environ["EVOX_STATE"])
    if args.command == "check":
        if not args.direction or not 1 <= args.timeout <= 600:
            parser.error("check requires direction and a timeout from 1 to 600 seconds")
        output = check(task, state, args.direction, args.note, args.timeout)
    elif args.command == "restore":
        output = restore(task, state)
    else:
        output = describe(read(state))
    print(json.dumps(output, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
