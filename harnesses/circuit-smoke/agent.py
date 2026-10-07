"""A real submitted harness for Catalyst's local circuit integration problem."""
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

HARNESS_ID = "circuit-smoke"


def checked_gates(candidate):
    gates = candidate.get("gates") if isinstance(candidate, dict) else None
    if not isinstance(gates, list) or not 1 <= len(gates) <= 100:
        raise ValueError("Expected between 1 and 100 gates.")
    for gate in gates:
        if (not isinstance(gate, list) or len(gate) != 3
                or any(type(bit) is not int for bit in gate)
                or sorted(gate) != [0, 1, 2]):
            raise ValueError("Each gate must use three distinct bits: 0, 1, 2.")
    for initial in range(8):
        bits = [(initial >> bit) & 1 for bit in range(3)]
        expected = [bits[0], bits[1], bits[2] ^ (bits[0] & bits[1])]
        for a, b, target in gates:
            bits[target] ^= bits[a] & bits[b]
        if bits != expected:
            raise ValueError("The proposed circuit failed a truth-table check.")
    return gates


def main():
    task = json.loads(Path(os.environ["CATALYST_TASK"]).read_text())
    if task["candidate_paths"] != ["candidate.json"]:
        raise ValueError("This harness supports the local circuit fixture only.")
    workspace = Path(task["workspace"])
    if not workspace.is_dir():
        raise ValueError("Missing task workspace.")
    prompt = task["instruction"] + (
        '\nReturn only JSON of the form {"gates": [[control_a, control_b, target], ...]}.'
        "\nUse as few gates as possible. Do not return a score."
    )
    request = Request(
        os.environ["OPENAI_BASE_URL"].rstrip("/") + "/chat/completions",
        data=json.dumps({
            "model": os.environ["CATALYST_MODEL"],
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 5000,
        }).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]},
    )
    with urlopen(request, timeout=30) as response:
        data = response.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise ValueError("Model response is too large.")
    text = json.loads(data)["choices"][0]["message"]["content"].strip()
    if text.startswith("```") and text.endswith("```"):
        text = "\n".join(text.splitlines()[1:-1])
    gates = checked_gates(json.loads(text))
    target = workspace / "candidate.json"
    temporary = workspace / "candidate.json.tmp"
    # The marker makes this example's output recognizable in the private capture.
    # Verification still checks the gates independently and binds the whole file.
    temporary.write_text(json.dumps({"gates": gates, "harness": HARNESS_ID}) + "\n")
    temporary.replace(target)
    print(json.dumps({"event": "candidate_written", "harness": HARNESS_ID, "gates": len(gates)}))


if __name__ == "__main__":
    main()
