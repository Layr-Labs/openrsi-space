# Deployment compatibility

The public package defaults to problem release `v2`, with 40 licensed PDFs bundled
for offline preparation. Before starting a new run, use `catalyst problem current`
to check the evaluator's active release and exact digest. Update the package if
that command reports a mismatch; pass the discovered tag with `--problem-release`.

A new manifest is not interchangeable with a historical problem hash. Existing
requests and receipts retain their original problem identity; never edit them to
match a newer release. Historical v1 catalogs remain unchanged. Do not use the
older production compatibility branch for new v2 submissions.

The evaluator's configured problem, worker package and receipt authorization must
be switched together. A repository update alone does not deploy the service.
Deployment procedures and current rollout evidence belong in catalyst-verifier.
