# Real ECDSA baseline harness

This executable leaves the pinned candidate unchanged and makes no model calls.
It tests source packaging and independent verification against the real ECDSA task.
It is a baseline, not an autonomous research improvement.

Use `catalyst harness build harnesses/ecdsa-baseline` and the [local smoke test](../../docs/local-evaluation.md).
Remote admission depends on the service's enabled baseline policy; do not assume
this fixture authorizes model access. Operator fixture setup lives in `catalyst-verifier`.
