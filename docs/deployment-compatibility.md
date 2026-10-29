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

## Local runtime compatibility

This client requires a runtime with `model-provider-registry-v1` and
`dungeness providers`, in addition to the existing execution and problem-service
capabilities. The earlier gateway-hardening pin `11e3f4c` does not provide provider
discovery. Upgrade and deploy the runtime together with the updated client.

If preparation reports a missing capability, create a fresh checkout at an unused
path; leave existing runs and working changes intact. The hosted runtime pin verified on 2026-10-29 is `840cf5cbd86a73e30d2130f278a1dbd725baa0b4`:

```sh
git clone https://github.com/Layr-Labs/dungeness.git /absolute/path/to/dungeness-compatible
git -C /absolute/path/to/dungeness-compatible checkout --detach 840cf5cbd86a73e30d2130f278a1dbd725baa0b4
/absolute/path/to/dungeness-compatible/dungeness capabilities
/absolute/path/to/dungeness-compatible/dungeness providers
```

Retry with `--dungeness /absolute/path/to/dungeness-compatible`. Do not merely edit
the capability declaration of an older runtime. Check the actual declarations and
provider output. A local pin does not establish which revision the hosted
evaluator uses; coordinate the release with its operator.

For a bug report, include `catalyst --version` and the Dungeness revision from
`git -C /absolute/path/to/dungeness rev-parse HEAD`. For a Catalyst source checkout,
also include `git -C /absolute/path/to/catalyst rev-parse HEAD` and whether it has
local changes: the package version alone does not distinguish development commits.
See the [changelog](../CHANGELOG.md) for unreleased client changes.
