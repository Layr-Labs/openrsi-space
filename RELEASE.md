# Production compatibility release — 2026-10-22

This branch preserves the existing unversioned ECDSA problem manifest and all
receipt identities while updating Dungeness compatibility checks to its explicit
runtime contract. It also records the required-public-source behavior already
running on the service. It does not activate the v0/v1 problem migration on main.

Runtime: `Layr-Labs/dungeness@5f547604e11d7f857f976b0893f0d29ee6487aa5`.
Pair with the matching `catalyst-verifier` branch
`release/catalyst-prod-20261022-runtime-cleanup`.

Validation: public package tests, private package tests with the real compiler,
and full Docker execution against a synthetic model provider, including
independent verification and repeat receipt retrieval through the Yukon CLI.
No paid model calls are used by these checks.
