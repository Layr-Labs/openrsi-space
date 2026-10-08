# Catalyst through unmodified Yukon

This follows Yukon's `docs/github-actions-benchmark-author-guide.md` and
`docs/pareto-mode.md`. The custom Yukon runner patches are not required.

## Workflow and readiness

1. `catalyst remote submit` uploads the harness to Catalyst for execution and
   independent verification. It returns a receipt and private traces.
2. The solver copies the receipt to `submission/verification.json`.
3. `yukon run` checks the existing receipt; it never starts an evaluation.
4. `yukon submit` uploads only the receipt. Yukon creates a candidate commit/PR
   and dispatches the repository's `benchmark.yml`.
5. The workflow authenticates with GitHub OIDC, retrieves the stored judgment,
   and uploads one trusted Pareto score artifact.
6. Yukon records its score and evidence. Pareto does not merge submissions.

The receipt endpoint and Yukon login are deployed on `openclaw` in release
`20261007-dev-pipeline-1` from commit `3e6b373`. The Linux suite passed 117 tests (three optional
integrations skipped). Solver keys are validated against **https://api-dev.yukon.org**.
Existing evaluations were preserved; legacy solver passwords are disabled.

OIDC tests use signed fixture tokens, not real GitHub-issued tokens. A complete
hosted run still requires configuring repository authorization and registering
the benchmark. The HTTPS workflow is published on `main`. The author installed the
dev Yukon Eigen App on `Layr-Labs/catalyst`, which is the correct App for this
integration. Production App access is not required.
A successful local preview does not establish
GitHub App permissions, hosted dispatch or the resulting Yukon leaderboard entry.

**HTTPS is now available at https://35.92.254.142.** Public certificate
validation, authenticated receipt retrieval and a certificate-renewal simulation
with Nginx reload have passed. The workflow calls that URL directly; it requires
no SSH connection, repository variables or saved API key. The OIDC repository
policy and GitHub-hosted runner connectivity still need verification.
See [the deployed HTTPS setup](https.md).

The included starter receipt refers to completed remote evaluation
`03586584-86c1-4b9d-9a09-1a13701efabe`, with scores `[10758874395, 0]` and model
access disabled. It belongs to the dev Yukon account and was executed and
independently verified on the VM.
Baseline registration retrieves it without running the harness.

## Author setup

Use the already-installed **Yukon Eigen** App on `Layr-Labs/catalyst` for dev:

https://github.com/apps/yukon-eigen/installations/new

The author also needs
Yukon benchmark-import permission. For a private repo, solvers need ordinary
GitHub read access. No custom Yukon release is needed.

The dev account's import preflight currently returns HTTP 403:
`this account is not allowed to import benchmarks`. A Yukon operator must
authorize the account for benchmark imports or perform the import. The
ordinary dev API key works for solver authentication; it does not grant this
author permission.

Publish the tested revision to `main`. Record its exact Git SHA and numeric
GitHub repository ID (different from a Yukon benchmark UUID):

```sh
gh api repos/Layr-Labs/catalyst --jq '{id,full_name,default_branch}'
git rev-parse HEAD
```

### Verifier connection

`.github/workflows/benchmark.yml` pins
`CATALYST_EVALUATOR_URL: https://35.92.254.142` as challenge-owned configuration.
Nginx terminates TLS on port 443 and forwards to the API on loopback port 8778.
When the service moves, update the trusted URL in the workflow and client setup.
The URL is public configuration; authentication uses a fresh GitHub OIDC token.
No solver key or SSH credential belongs in the workflow.

The `ubuntu-latest` runner needs outbound access to the verifier, GitHub OIDC
and package downloads. It only retrieves receipts; no dedicated GitHub runner,
Agent Compose or new cloud resource is needed.

### Deployment and authorization

Deploy the tested Catalyst source to a new VM release and install its locked
dependencies. Preserve `/var/lib/catalyst/evaluator`, jobs and tokens. Configure
the published baseline before importing:

```sh
sudo -u catalyst /opt/catalyst/current/.venv/bin/catalyst \
  --state /var/lib/catalyst/evaluator/service github-configure \
  --auth-file /var/lib/catalyst/evaluator/auth.json \
  --repository Layr-Labs/catalyst \
  --repository-id "<numeric GitHub repository ID>" \
  --yukon-api https://api-dev.yukon.org \
  --baseline-evaluation 03586584-86c1-4b9d-9a09-1a13701efabe \
  --baseline-sha "<published baseline commit SHA>"
```

Restart the screen-managed API after configuration changes. This command
preserves existing credentials and creates an explicit baseline binding.
Baseline lookup accepts only the configured repository/workflow, Yukon's
`yukon/baseline/<SHA>` branch, exact SHA and receipt. It does not invent a solver
submission identity. Yukon creates that baseline branch from the published
revision during import.

Import through Yukon's author UI or its existing script, supplying the author's
Yukon API token privately. From an unmodified Yukon checkout:

```sh
bun scripts/import-benchmark.ts https://github.com/Layr-Labs/catalyst \
  --api https://api-dev.yukon.org --name bxue-l2/catalyst
```

Wait for successful GitHub and Yukon baseline checks. Copy the assigned
benchmark UUID and rerun `github-configure` with the same arguments plus
`--benchmark-id "<UUID>"`. Restart the service, then open the ready benchmark
through the author UI.

For ordinary submissions, Catalyst reads the ID from the OIDC-authenticated
`refs/heads/submissions/<UUID>` ref. It checks owner and benchmark through
Yukon's existing `GET /api/submissions/<UUID>` API. It never trusts an owner
claim in a receipt. If Yukon visibility requires an authenticated read, provision
a service-readable Yukon key in the private policy's `yukon_api_token` field.

## Solver commands

Use stock Yukon with the dev login and registered benchmark name:

```sh
export YUKON_API_URL=https://api-dev.yukon.org
yukon clone bxue-l2/catalyst catalyst-solver
cd catalyst-solver
uv sync --frozen
yukon setup
mkdir -p .catalyst
cp -R harnesses/ecdsa-baseline .catalyst/my-harness
export CATALYST_EVALUATOR_URL=https://35.92.254.142
# Use your existing Yukon login or supply YUKON_API_TOKEN privately.
unset CATALYST_API_TOKEN
# The baseline evaluation configuration is allowed by the model-disabled policy.

uv run catalyst remote submit .catalyst/my-harness --wait
cp .catalyst/my-harness/verification.json submission/verification.json
yukon run
yukon submit --note-file submission-note.md \
  --model "<exact model used, or disabled for this baseline>" \
  --harness "ecdsa-baseline"
yukon submissions --all --json
```

Use your Yukon login; the client exchanges it for a short-lived solver session.
A model-disabled baseline is not an optimization claim.
Notes must meet Yukon's current requirements and contain no secrets.

A fresh evaluation produces a new receipt and a normal candidate diff.
Submitting the unchanged starter receipt may fail Yukon's normal no-change rule.
If local source changed during evaluation, copy the receipt from the exact
path printed by the client rather than assuming it was exported beside it.

Successful end-to-end validation requires all three: a completed remote
evaluation with independent verification, a successful GitHub submission workflow
with exactly one score artifact, and matching scores/harness digest recorded in
Yukon's API (`officialMetrics.remoteVerification` and normal evaluation evidence).

## Limits

- The ECDSA MVP has model access disabled. Temporary provider-access handoff
  and its memory-only lifecycle are not implemented. Do not send provider secrets to it.
- Missing, foreign or altered receipts, wrong problems/policies, and failed owner
  lookups write no score. The client clears stale score files first.
- Receipt lookup is replay-safe and never enqueues evaluations. Repository
  permissions default to disabled and must be provisioned by an operator.
- This MVP handles initial import and ordinary submissions. Reorgs using separate
  execution IDs need an additional trusted mapping to the original submission;
  unknown IDs fail closed without rerunning a harness.
- A future credential endpoint requires authenticated HTTPS and run-scoped,
  memory-only access. Never persist user provider credentials, even encrypted.
  Renewal stays on the user's machine; completion, failure, cancellation and
  expiry discard access. Restart requires fresh authorization. See
  [runtime requirements](runtime-platform-requirements.md).

## Local tests

```sh
uv sync --frozen
uv run python -m unittest discover -s tests
CATALYST_STOCK_YUKON=/path/to/unmodified/yukon \
  uv run python -m unittest discover -s tests -p test_github_receipts.py
```

The optional CLI test needs that checkout's locked dependencies installed. These
fixture tests remain distinct from the live GitHub/App/network checks above.
