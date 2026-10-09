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
only that receipt. Use `catalyst yukon-submit` for the current Pareto flow: it
calls stock Yukon and binds the resulting execution ID through the authenticated
existing job API. See the end-to-end guide for the full command.

Yukon creates the Pareto candidate commit and dispatches the challenge-owned
`.github/workflows/benchmark.yml`. That workflow authenticates with GitHub OIDC
and calls `POST /verifications/retrieve` on Catalyst. The verifier checks the
configured repository, problem/version, receipt and stored harness digest. It
resolves the submission owner and benchmark through Yukon's existing API.
The returned standard Pareto artifact is recorded by Yukon's existing runner.
Retrieval never starts another harness execution. Pareto submissions are not merged.

The GitHub runner reaches the existing VM over public HTTPS on port 443.
The service remains
screen-managed; a workflow needs no new VM or long-lived API credential.

## Scores and tiers

The manifest has two minimizing objectives:
`[best_verified_performance, model_credits_at_that_capture]`, where performance
is `avg_toffoli * peak_qubits`. Invalid results use a null whole tuple. Individual
tuple components must be finite numbers; missing tier observations stay in
metadata. Tiers are **$20, $200 and Best achieved**, not separate tracks with
overlapping editable paths.

The public metrics preserve the full verified performance/cost curve and trusted
budget summaries. The solver chooses one spending cap; $20, $200 and best overall
are views over the saved Dungeness history. A cheaper run qualifies for both
budget views. See [budget accounting](../../docs/tier-accounting.md).

## Current challenge UI

`challenge-ui.patch` and `challenge-ui-base-revision.txt` contain the new
ECDSA-only board for stock Yukon's Challenges UI. This is a UI patch; it does not
change the backend, CLI, API authentication or worker.
The local preview is `.catalyst/yukon-publish` at `/catalyst`. See
[UI setup and handoff](../../docs/challenge-ui.md) for the command and hosting
configuration. The preserved patches below are older prototypes.

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

The receipt API, signed fixture JWTs, ownership/problem checks and stock Yukon
CLI are covered locally. A real Codex/ChatGPT evaluation and hosted Yukon dev
submission also succeeded, including GitHub OIDC retrieval of the stored scores.
Complete history export and the cheat filter are deployed on the verifier. The
UI is tested against the real dev results and published as a source branch for
Yukon integration; public UI hosting remains separate. Provider credential
renewal and user cancellation remain later work.
