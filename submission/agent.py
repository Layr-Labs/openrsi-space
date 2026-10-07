"""Starter entrypoint: validate task input and retain the starting candidate.

Replace this with an autonomous solver and add its toolchains to Dockerfile.
End-to-end evaluation uses the remote gateway and pinned problem workspaces.
This starting harness makes no model calls and does not improve either candidate.
"""
import json
import os
from pathlib import Path

task = json.loads(Path(os.environ["CATALYST_TASK"]).read_text())
workspace = Path(task["workspace"])
if not workspace.is_dir():
    raise SystemExit("Workspace is missing.")
for relative in task["candidate_paths"]:
    if not (workspace / relative).exists():
        raise SystemExit(f"Candidate path is missing: {relative}")
print(json.dumps({"status": "completed", "problem": task["problem"],
                  "candidate_paths": task["candidate_paths"]}))
