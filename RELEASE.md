# Production compatibility release — 2026-10-22

This branch preserves the existing unversioned ECDSA problem manifest and all
receipt identities while updating Dungeness compatibility checks to its explicit
runtime contract. It also records the required-public-source behavior already
running on the service. It does not activate the v0/v1 problem migration on main.

Runtime: `Layr-Labs/dungeness@a555af561723e49f0a277fd606253ee9e5cbff4a`.
Pair with the matching `catalyst-verifier` branch
`release/catalyst-prod-20261022-runtime-cleanup`.

Validation: public package tests, private package tests with the real compiler,
and full Docker execution against a synthetic model provider, including
independent verification and repeat receipt retrieval through the Yukon CLI.
No paid model calls are used by these checks.

The second cleanup release moves record persistence into Dungeness records.py
and installs the ECDSA scaffold from Catalyst’s public problem assets. It requires
`declarative-scaffolds-v2`. The scaffold Docker end-to-end test checks a fresh
candidate, trusted edits, model accounting, independent verification and receipts.
