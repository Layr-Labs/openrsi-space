"""Trusted exhaustive verifier for a 3-bit Toffoli circuit integration fixture."""
import json
from pathlib import Path

logs = Path("/logs/verifier")
logs.mkdir(parents=True, exist_ok=True)
try:
    gates = json.loads(Path("/workspace/repo/candidate.json").read_text())["gates"]
    assert isinstance(gates, list) and 0 < len(gates) <= 100
    for gate in gates:
        assert isinstance(gate, list) and len(gate) == 3
        assert all(type(bit) is int for bit in gate) and sorted(gate) == [0, 1, 2]
    for initial in range(8):
        bits = [(initial >> bit) & 1 for bit in range(3)]
        expected = [bits[0], bits[1], bits[2] ^ (bits[0] & bits[1])]
        for a, b, target in gates:
            bits[target] ^= bits[a] & bits[b]
        assert bits == expected
    result = {"valid": True, "status": "ok", "avg_toffoli": len(gates),
              "peak_qubits": 3, "score": len(gates) * 3}
except (OSError, ValueError, KeyError, TypeError, AssertionError):
    result = {"valid": False, "status": "invalid", "reason": "Circuit truth table failed."}
(logs / "score.json").write_text(json.dumps(result))
(logs / "reward.json").write_text(json.dumps({"ecdsafail_score": result.get("score", 0)}))
