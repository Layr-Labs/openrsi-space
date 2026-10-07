"""Submit the actual ecdsa.fail starting module unchanged; no model requests."""
import hashlib
import json
import os
from pathlib import Path

task = json.loads(Path(os.environ["CATALYST_TASK"]).read_text())
if task["candidate_paths"] != ["src/point_add"]:
    raise SystemExit("This harness requires the real ECDSA point-add module.")
candidate = Path(task["workspace"]) / "src/point_add"
files = sorted(candidate.rglob("*.rs"))
if not files or candidate.is_symlink() or any(path.is_symlink() for path in candidate.rglob("*")):
    raise SystemExit("The pinned ECDSA module is missing or contains symlinks.")
print(json.dumps({
    "harness": "ecdsa-baseline", "status": "retained_pinned_candidate", "model_calls": 0,
    "files": {path.relative_to(candidate).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in files},
}))
