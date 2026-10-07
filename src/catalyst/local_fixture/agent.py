"""Offline integration harness for a tiny reversible-circuit task, not ECDSA."""
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

task = json.loads(Path(os.environ["CATALYST_TASK"]).read_text())
request = Request(
    os.environ["OPENAI_BASE_URL"] + "/chat/completions",
    data=json.dumps({"model": os.environ["CATALYST_MODEL"],
                     "messages": [{"role": "user", "content": task["instruction"]}],
                     "max_tokens": 5000}).encode(),
    headers={"Content-Type": "application/json", "Authorization": "Bearer testbed"},
)
with urlopen(request, timeout=20) as response:
    answer = json.load(response)
candidate = json.loads(answer["choices"][0]["message"]["content"])
Path(os.environ["CATALYST_WORKSPACE"], "candidate.json").write_text(json.dumps(candidate))
# A false stdout score must never influence the independent verifier.
print('{"performance": 0, "claimed_score": 0}')
