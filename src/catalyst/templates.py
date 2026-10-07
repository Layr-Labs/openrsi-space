"""Small editable authoring templates; these are not Dungeness runtime code."""

INSTRUCTIONS = """# Problem

Implement `solve(number)` in `solution.py` to return the square of an integer.
The evaluation metric is the fraction of test cases answered correctly.

Replace this example with your research question, assumptions, allowed outputs,
and evaluation criteria. Keep the source repository and verifier in sync.
"""

SOLUTION = """def solve(number):
    # Replace this starting candidate with your own implementation.
    return 0
"""

CHECKER = """# Trusted evaluator, copied from the pinned source repository.
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("candidate", sys.argv[1])
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)
cases = [-19, -2, 0, 1, 7, 53]
correct = sum(candidate.solve(n) == n * n for n in cases)
print(correct / len(cases))
"""

DOCKERFILE = """FROM python:3.12-slim
COPY evaluator/ /opt/evaluator/
COPY grade.py /tests/grade.py
COPY test.sh /tests/test.sh
RUN mkdir -p /logs/verifier && chmod 0555 /tests/test.sh
RUN groupadd --gid 10001 candidate && useradd --no-create-home --uid 10001 --gid 10001 candidate
CMD ["/tests/test.sh"]
"""

TEST_SH = """#!/bin/sh
set -eu
exec python3 /tests/grade.py
"""

GRADE = """# Minimal example grader. Replace it with your problem's trusted evaluation.
import json
import os
from pathlib import Path
import subprocess
import sys

logs = Path("/logs/verifier")
logs.mkdir(parents=True, exist_ok=True)
candidate = Path("/workspace/repo/solution.py")
worker = "import json,runpy,sys; ns=runpy.run_path(sys.argv[1]); print(json.dumps(ns['solve'](int(sys.argv[2]))))"
def unprivileged():
    os.setgroups([])
    os.setgid(10001)
    os.setuid(10001)

cases = [-19, -2, 0, 1, 7, 53]
correct = 0
for number in cases:
    try:
        result = subprocess.run(
            [sys.executable, "-I", "-c", worker, str(candidate), str(number)],
            capture_output=True, text=True, timeout=5, check=True, preexec_fn=unprivileged,
        )
        answer = json.loads(result.stdout)
        correct += type(answer) is int and answer == number * number
    except Exception:
        pass
score = correct / len(cases)
document = {"score": score, "valid": True}
(logs / "score.json").write_text(json.dumps(document))
(logs / "reward.json").write_text(json.dumps({"score": score}))
"""
