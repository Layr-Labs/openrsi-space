# ECDSA research harness

Inspect the pinned Rust point-add module. Find and implement a small correctness-
preserving circuit improvement, minimizing average Toffoli count times peak
qubits. Use the provided evaluation sidecar for feedback. Keep the best checked
candidate; if no improvement is verified locally, retain the starting candidate.
An independent platform verifier, not this harness, decides the official score.
