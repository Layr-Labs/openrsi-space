"""Adapt EvoX's maximized fitness to independently verified ECDSA candidates."""
import json
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tempfile
import threading


def load_task():
    return json.loads(Path(os.environ["CATALYST_TASK"]).read_text())


def decode_candidate(text):
    document = json.loads(text)
    edits = document.get("edits") if isinstance(document, dict) else None
    if not isinstance(edits, list) or len(edits) > 200:
        raise ValueError("Expected a bounded edits list.")
    total = 0
    for edit in edits:
        if not isinstance(edit, dict) or set(edit) != {"path", "old", "new"}:
            raise ValueError("Each edit requires path, old and new.")
        name = edit["path"]
        if not isinstance(name, str):
            raise ValueError("Edit path must be a string.")
        path = PurePosixPath(name)
        if (path.is_absolute() or ".." in path.parts or "\\" in name
                or str(path) != name or path.suffix != ".rs"
                or not isinstance(edit["old"], str) or not edit["old"]
                or not isinstance(edit["new"], str) or edit["new"] == edit["old"]):
            raise ValueError("Expected canonical relative Rust filenames.")
        total += len(edit["old"].encode()) + len(edit["new"].encode())
    if total > 1024 * 1024:
        raise ValueError("Edits must fit in 1 MiB.")
    return edits


def apply_edits(original, edits):
    replacements = {}
    for edit in edits:
        name, old = edit["path"], edit["old"]
        if name not in original:
            raise ValueError("Edit names a file outside the original candidate.")
        text = original[name]
        start = text.find(old)
        if start < 0 or text.find(old, start + 1) >= 0:
            raise ValueError("Each old string must match exactly once in the original file.")
        end = start + len(old)
        spans = replacements.setdefault(name, [])
        if any(start < other_end and other_start < end for other_start, other_end, _ in spans):
            raise ValueError("Edits must not overlap.")
        spans.append((start, end, edit["new"]))
    files = dict(original)
    for name, spans in replacements.items():
        text = files[name]
        for start, end, replacement in sorted(spans, reverse=True):
            text = text[:start] + replacement + text[end:]
        files[name] = text
    return files


def verify(path):
    response = subprocess.run(["evaluate", "--json", str(path)], check=True,
                              capture_output=True, text=True, timeout=590)
    return json.loads(response.stdout)


def valid_score(result):
    score = result.get("score")
    return (result.get("status") == "ok" and type(score) in (int, float)
            and math.isfinite(score) and score > 0)


class CandidateEvaluator:
    def __init__(self, task):
        self.workspace = Path(task["workspace"]).resolve()
        if task["candidate_paths"] != ["src/point_add"]:
            raise ValueError("This adapter expects the ECDSA point_add directory.")
        self.candidate = self.workspace / "src/point_add"
        self.root = self.workspace / ".catalyst-evox"
        self.seed = self.root / "initial.json"
        self.lock = threading.Lock()
        self.best_score = self.baseline_score = None

    def initialize(self):
        self.root.mkdir()  # Never silently mix two runs' local search state.
        self.original = {p.relative_to(self.candidate).as_posix(): p.read_text()
                         for p in self.candidate.rglob("*.rs")}
        if "mod.rs" not in self.original:
            raise ValueError("Candidate requires mod.rs.")
        self.seed.write_text('{"edits": []}\n')
        result = verify(self.candidate)
        if not valid_score(result):
            raise RuntimeError("Pinned starting candidate failed trusted evaluation.")
        self.best_score = self.baseline_score = result["score"]

    def context(self):
        # Bounded source context for a small smoke budget; the complete original
        # directory is still materialized for every verification.
        return "\n\n".join(f"FILE {name} ({len(text)} characters; excerpt)\n{text[:10000]}"
                           for name, text in sorted(self.original.items()))[:30000]

    def evaluate(self, program_path):
        try:
            path = Path(program_path)
            if path.stat().st_size > 2 * 1024 * 1024:
                raise ValueError("Candidate document is too large.")
            files = apply_edits(self.original, decode_candidate(path.read_text()))
            with tempfile.TemporaryDirectory(dir=self.root, prefix="candidate-") as temporary:
                candidate = Path(temporary)
                for name, content in files.items():
                    target = candidate / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(content)
                result = verify(candidate)
                if not valid_score(result):
                    return {"combined_score": 0.0, "artifacts": {"feedback": json.dumps(result)}}
                score = result["score"]
                with self.lock:
                    if score < self.best_score:
                        shutil.rmtree(self.candidate)
                        shutil.copytree(candidate, self.candidate)
                        self.best_score = score
                return {"combined_score": self.baseline_score / score,
                        "artifacts": {"feedback": json.dumps(result)}}
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            return {"combined_score": 0.0, "artifacts": {"feedback": str(error)}}
