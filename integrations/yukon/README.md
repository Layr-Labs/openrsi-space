# Yukon challenge integration

Catalyst uses stock Yukon's **GitHub Actions runner and Pareto mode**. No Yukon
core, CLI or backend patch is required. Follow the
[complete end-to-end guide](../../docs/github-actions-e2e.md) for GitHub App
installation, verifier connectivity, deployment, registration and solver commands.

## Current contract

The solver first submits harness source with `catalyst remote submit --wait`.
Catalyst executes it and independently verifies the result. The solver copies
its receipt into `submission/verification.json`, the only editable path in
`benchmark.json`. `yukon run` previews the existing result; `yukon submit` uploads
only that receipt.

Yukon creates the candidate commit and PR, then dispatches the challenge-owned
`.github/workflows/benchmark.yml`. That workflow authenticates with GitHub OIDC
and calls `POST /verifications/retrieve` on Catalyst. The verifier checks the
configured repository, problem/version, receipt and stored harness digest. It
resolves the submission owner and benchmark through Yukon's existing API.
The returned standard Pareto artifact is recorded by Yukon's existing runner.
Retrieval never starts another harness execution. Pareto submissions are not merged.

For the private MVP, a restricted SSH tunnel connects the GitHub runner to the
existing VM. An HTTPS endpoint on port 443 is also supported. The service remains
screen-managed; a workflow needs no new VM or long-lived API credential.

## Scores and tiers

The manifest has two minimizing objectives:
`[best_verified_performance, model_credits_at_that_capture]`, where performance
is `avg_toffoli * peak_qubits`. Invalid results use a null whole tuple. Individual
tuple components must be finite numbers; missing tier observations stay in
metadata. Tiers are **$20, $200 and Best achieved**, not separate tracks with
overlapping editable paths.

The public metrics preserve the full verified performance/cost curve and trusted
tier summaries. Yukon's generic Pareto order does not itself implement the
checkpoint leaderboard. See [tier accounting](../../docs/tier-accounting.md).
Continuous versus independent tier execution remains a scheduling decision;
the model-disabled MVP validates the transport and real ECDSA verification.

## Preserved prototypes

`remote-verification.patch`, `remote-verification-base-revision.txt`, and
`remote-verification-v1.schema.json` preserve the earlier direct-backend provider
prototype. The modified Yukon checkout and its local API tests also remain
available. These changes are **not needed by the current integration** and must
not be applied as a prerequisite for the GitHub workflow.

`catalyst-challenge.patch`, `base-revision.txt`, and the older
`.catalyst/yukon-integration/` preview preserve an earlier multi-problem board.
That preview predates the current ECDSA contract and is not the launch viewer.
The current local viewer is available with `catalyst demo` and `catalyst serve`.

## Validation and remaining work

The receipt API, signed fixture JWTs, ownership/problem checks and an unmodified
Yukon CLI are covered locally. The fixture checks do not establish real GitHub
OIDC, App permissions, publication or hosted Yukon connectivity.

The live acceptance test must complete remote harness verification, a successful
GitHub submission workflow, and matching scores plus harness identity in Yukon's
API. See the end-to-end guide for current setup requirements. Provider credential
upload/renewal, funded model execution and runtime checkpoint collection remain
separate work after the model-disabled MVP.
