# Catalyst through unmodified Yukon

This follows Yukon's `docs/github-actions-benchmark-author-guide.md` and
`docs/pareto-mode.md`. The custom Yukon runner patches are not required.

## Workflow and readiness

1. `catalyst remote submit` uploads the harness to Catalyst for execution and
   independent verification. It returns a receipt and private traces.
2. The solver copies the receipt to `submission/verification.json`.
3. `yukon run` checks the existing receipt; it never starts an evaluation.
4. `catalyst yukon-submit` calls stock `yukon submit` to upload only the receipt,
   then verifies and registers its execution/submission mapping with Catalyst.
   Yukon creates a candidate commit and dispatches the repository's `benchmark.yml`.
5. The workflow authenticates with GitHub OIDC, retrieves the stored judgment,
   and uploads one trusted Pareto score artifact.
6. Yukon records its score and evidence. Pareto does not merge submissions.

The receipt endpoint, Yukon login and native Codex execution are deployed on
`openclaw`, with workflow identity and Pareto job mapping in release
`20261008-history-screen-1`, which also exports intermediate ECDSA history and
screens candidate source. The last full local suite passed
151 tests (one Linux-only check skipped), including stock Yukon and native
Dungeness contracts. Solver keys are validated against **https://api-dev.yukon.org**.
Existing evaluations were preserved; legacy solver passwords are disabled.

The active **open** Yukon dev benchmark is `layr-labs/catalyst`, UUID
`8d3a2daa-afab-4685-b93a-7443c83049d2`, in Pareto mode. Its initial evaluation is
`b29b2832-d0e7-4612-ae60-93706d971928`. The hosted baseline workflow
[37854296673](https://github.com/Layr-Labs/catalyst/actions/runs/37854296673)
passed, and Yukon ingested the baseline judgment. This exercised real GitHub OIDC,
the public HTTPS connection, receipt retrieval, artifact upload, and Yukon ingestion.
The configured GitHub repository ID is `1402357635`; the pinned baseline source is
`2411bd8c64c04023a14645dcf6578e3a7b9e6fae`.

Two earlier empty failed registrations were archived during the authorized recovery:
`14c194b3-305a-4aaa-a094-c624bbdbcfb4` and
`f103643a-e478-4675-a077-d8eb0045bb1c`. Their records remain in Yukon history and
`.catalyst/yukon-dev-registration/`; do not use those UUIDs for new configuration.
Full upstream Action SHAs resolved the enterprise action-policy rejection.
The verifier now accepts direct-workflow `job_workflow_ref`/`job_workflow_sha`
claims only when they match the already authorized workflow and revision.
All 67 related authentication, receipt, binding, resume and API tests passed,
including stock Yukon and rejection of foreign owners, workflows or revisions.
The local `fix/initial-baseline-retry` Yukon patch is unused. No custom Yukon
backend or worker was deployed.
The HTTPS workflow is published on `main`. The author installed the
dev Yukon Eigen App on `Layr-Labs/catalyst`, which is the correct App for this
integration. Production App access is not required.
A successful local preview does not establish
GitHub App permissions, hosted dispatch or the resulting Yukon leaderboard entry.

**HTTPS is now available at https://35.92.254.142.** Public certificate
validation, authenticated receipt retrieval and a certificate-renewal simulation
with Nginx reload have passed. The workflow calls that URL directly; it requires
no SSH connection, repository variables or saved API key. The OIDC repository
policy and GitHub-hosted runner connectivity passed the hosted baseline.
See [the deployed HTTPS setup](https.md).

The included starter receipt refers to completed remote evaluation
`03586584-86c1-4b9d-9a09-1a13701efabe`, with scores `[10758874395, 0]` and model
access disabled. It belongs to the dev Yukon account and was executed and
independently verified on the VM.
Baseline registration retrieves it without running the harness.

The full solver flow passed with real-model evaluation
`21045450-81c5-4742-bb9c-628ff30a6606`: Yukon submission
`8c672862-fdce-43fe-a66c-09ce10bf24b2` records `valid: true` and scores
`[10704574395, 0.887796]`, with the matching harness digest. GitHub run
[37869431621](https://github.com/Layr-Labs/catalyst/actions/runs/37869431621)
succeeded. That first publication used manual promotion. The current manifest
uses **automatic** acceptance after remote verification; existing benchmarks
must adopt this change through Yukon's Pareto reorg, preserving the benchmark ID.
No additional model evaluation was started during publication.

The history/screening release also passed the complete hosted flow with remote
evaluation `f0dc32fc-a17c-48b5-9dca-d10414023159`, Yukon submission
`198b4e96-827e-48ed-9b8f-3a498db316a2`, and GitHub run
[37879400510](https://github.com/Layr-Labs/catalyst/actions/runs/37879400510).
Yukon recorded the exact source digest, all six curve points, and the score pair
`[10758874395, 0.674814]`. Total usage for that run was **1.602784** credits;
0.674814 is the cost when its best result was first verified. It did not beat
the prior run's circuit score.

That test had a three-credit aggregate allowance. Its first attempt,
`4958d55a-988c-4ce3-8f38-74ffe2fc0a90`, used **1.117388** credits and was rejected
for exceeding the inherited 100,000-token limit. Its record was preserved.
The corrected attempt used a 1.85-credit cap and a 1,000,000-token secondary
ceiling. Actual combined spending was **2.720172** credits. No extra model run
was made during Yukon publication. The matrix displays the valid replacement
in all three budget columns and shows all six observations, without a review
status column.

### Hosted fake-score rejection

A separate authorized negative test submitted a fabricated receipt directly
through stock Yukon, claiming score `1`, without creating a remote evaluation.
The fake evaluation ID was `d44b5b65-ea88-4599-aef4-6b3418ee73e1`; its absence
from the service's job store was checked.

The local receipt verifier returned **HTTP 404** and removed a pre-existing
fake score file. Hosted GitHub run
[37879719498](https://github.com/Layr-Labs/catalyst/actions/runs/37879719498)
also failed at receipt retrieval with **HTTP 404**. Yukon submission
`5ec54681-6799-4206-b5a2-808db8e9d249` finished **failed**, with its untrusted
`claimedScore: 1` retained for audit but `judgment`, `officialMetrics`, and
`evaluation` all null. Browser verification confirmed it is absent from the
matrix. No model credits were used for this rejection test.
The positive workflow produced exactly one `catalyst-score` artifact; the
negative workflow produced no artifacts.

## Author setup

Use the already-installed **Yukon Eigen** App on `Layr-Labs/catalyst` for dev:

https://github.com/apps/yukon-eigen/installations/new

The author also needs
Yukon benchmark-import permission. For a private repo, solvers need ordinary
GitHub read access. No custom Yukon release is needed.

The dev account's importer permission was confirmed on October 8: an empty
import request now reaches schema validation instead of being rejected by the
importer allowlist. No benchmark was created by that preflight. Solver login
and benchmark-import permission remain separate authorizations.

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
  --repository-id 1402357635 \
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

After configuring the baseline authorization, import through Yukon's author UI
or its existing script, supplying the author's Yukon API token privately.
The dev benchmark is already open; do not import another copy. For a future fresh
installation, check for an existing active `layr-labs/catalyst` before importing.
From an unmodified Yukon checkout:

```sh
bun scripts/import-benchmark.ts https://github.com/Layr-Labs/catalyst \
  --api https://api-dev.yukon.org --name layr-labs/catalyst
```

Wait for successful GitHub and Yukon baseline checks. Copy the assigned
benchmark UUID and rerun `github-configure` with the same arguments plus
`--benchmark-id "<UUID>"`. Restart the service, then open the ready benchmark
through the author UI.

For Pareto submissions, the OIDC-authenticated
`refs/heads/submissions/<UUID>` ref contains an **execution ID**, not the public
submission ID. The helper sends the returned job ID and receipt to
`POST /verifications/yukon-bind`. Catalyst calls the configured Yukon's authenticated
`GET /api/jobs/<job-id>` endpoint with the solver's transient key. It checks job kind,
owner, benchmark, source repository and verified receipt before recording an immutable
mapping. The key and private job archive URL are never persisted.

During workflow retrieval, Catalyst uses that mapping to check the public submission's
current owner, benchmark and cancellation state through
`GET /api/submissions/<submission-id>`. The receipt supplies no trusted owner claim.
GitHub receives no solver key. A future public, trusted Yukon execution lookup API could
replace the helper's binding step; no such Yukon change is required for this MVP.

## Solver commands

For first-time login, see [token types and credential setup](live-models.md#which-token-and-where-does-it-come-from).

Use current stock Yukon with the dev login and registered benchmark name.
Older CLI releases can reject the Pareto manifest with `Invalid benchmark manifest`;
update the CLI first:

```sh
export YUKON_API_URL=https://api-dev.yukon.org
yukon update
yukon clone layr-labs/catalyst catalyst-solver
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
uv run catalyst yukon-submit --no-dependencies --note-file submission-note.md \
  --model "<exact model used, or disabled for this baseline>" \
  --harness "ecdsa-baseline"
yukon submissions --all --json
```

Use your Yukon login; the client exchanges it for a short-lived solver session.
A model-disabled baseline is not an optimization claim.
Notes must meet Yukon's current requirements and contain no secrets.
Use `--dependencies-file` instead of `--no-dependencies` when reusing a prior
Yukon submission.

The helper saves its pending job locally before binding. Repeat the same helper
command after a binding failure to resume without uploading a second submission.
If the upload outcome is unknown, it stops and asks you to inspect existing Yukon
submissions first. To bind an already-submitted job manually:

```sh
uv run catalyst yukon-bind --job-id "<job UUID returned by Yukon>" \
  --benchmark-id 8d3a2daa-afab-4685-b93a-7443c83049d2
```

Keep the exact receipt in `submission/verification.json`. If the GitHub job has already
failed before binding, rerunning GitHub alone does not update a finished Yukon validation;
a new authorized submission or Yukon-supported recovery is needed.

A fresh evaluation produces a new receipt and a normal candidate diff.
Submitting the unchanged starter receipt may fail Yukon's normal no-change rule.
If local source changed during evaluation, copy the receipt from the exact
path printed by the client rather than assuming it was exported beside it.

Successful end-to-end validation requires all three: a completed remote
evaluation with independent verification, a successful GitHub submission workflow
with exactly one score artifact, and matching scores/harness digest recorded in
Yukon's API (`officialMetrics.remoteVerification` and normal evaluation evidence).

## Limits

- Baseline runs have model access disabled. The optional
  [temporary ChatGPT route](live-models.md) requires operator enablement and
  `--codex-auth-file`; no provider secret belongs in a workflow or receipt.
- Missing, foreign or altered receipts, wrong problems/policies, and failed owner
  lookups write no score. The client clears stale score files first.
- Receipt lookup is replay-safe and never enqueues evaluations. Repository
  permissions default to disabled and must be provisioned by an operator.
- This MVP handles initial import and ordinary submissions through the helper.
  Operator-triggered reorgs require new authenticated job mappings; those are not
  registered automatically. Unknown execution IDs fail closed without rerunning a harness.
- Provider-token handoff requires authenticated HTTPS and one-evaluation,
  memory-only access. Never persist user provider credentials, even encrypted.
  Completion, failure and expiry discard access; restart loses queued tokens.
  Renewal and user cancellation remain unimplemented. See
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

### Updating the automatic-acceptance policy

The manifest uses `promotionMode: automatic`. For an existing Pareto benchmark,
use the owner's reorg endpoint, retaining its UUID. A validity-only reorg
(`paretoScope: {scores: false, validity: "fresh"}`) retains scores and verifies
receipts under the new revision. It never starts another Dungeness run.

Authorize the exact new baseline commit with `github-configure` before starting.
Receipt bindings are immutable per Yukon execution, with the original submission
retained for ownership checks and audit. Each explicitly authorized baseline
revision also has a distinct retrieval identity; previous evidence remains intact.
Yukon's current reorg API returns baseline job IDs but not replay job IDs. An
operator must authorize the exact replay branches after checking their GitHub
App origin, pinned parent, receipt-only diff and existing receipt/owner binding.
Keep an audit of those exact revisions; never allow an arbitrary branch or owner.
Resume the benchmark only after the reorg reports ready and the genuine scores
and fabricated-score rejection have been checked.
