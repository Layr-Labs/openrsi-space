# Deployment compatibility

The public package defaults to problem release `v1`, with eight licensed PDFs bundled
for offline preparation. Before starting a new run, use `catalyst problem current`
to check the evaluator's active release and exact digest. Update the package if
that command reports a mismatch; pass the discovered tag with `--problem-release`.

A new manifest is not interchangeable with a historical problem hash. Existing
requests and receipts retain their original problem identity; never edit them to
match a newer release. The eight-paper collection replaces the prelaunch 40-paper library while retaining
the human-readable tag `v1` by operator request. Exact hashes distinguish these
collections and their evaluation records; the tag alone is not a compatibility
claim. Update the public package before submitting against the new digest.


The evaluator's configured problem, worker package and receipt authorization must
be switched together. A repository update alone does not deploy the service.
Deployment procedures and current rollout evidence belong in catalyst-verifier.
