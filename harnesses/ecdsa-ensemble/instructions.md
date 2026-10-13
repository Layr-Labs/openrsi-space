Improve the ECDSA point-addition module. Two independent Python workers propose
changes, submit immutable snapshots to the provided evaluator, and retain the
best independently verified candidate. The harness uses direct model API calls,
without Codex, and stops after one generation of two proposals.
