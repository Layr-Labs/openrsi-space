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

The receipt-only endpoint is deployed on `openclaw` in release
`20261007-github-actions-1`. Its Linux suite passed 108 tests (three optional
integrations skipped). Stock `yukon run` retrieved the real stored ECDSA result
through a private tunnel, with the expected scores and harness digest, without
starting an evaluation. Existing jobs and credentials were preserved.

OIDC tests use signed fixture tokens, not real GitHub-issued tokens. A complete
hosted run still requires configuring repository authorization and the workflow
connection and registering the benchmark. The author confirmed that the Yukon
Eigen App's access to `Layr-Labs/catalyst` was saved on October 7, 2026.
A successful local preview does not establish
GitHub App permissions, hosted dispatch or the resulting Yukon leaderboard entry.
The dedicated CI SSH key and host pin have also been tested from the Mac against
the VM using the workflow's connection script: verifier access succeeds, while
shell commands, other ports and remote listeners are denied. GitHub-hosted
runner connectivity and repository secret configuration remain unverified.

The included starter receipt refers to completed remote evaluation
`03586584-86c1-4b9d-9a09-1a13701efabe`, with scores `[10758874395, 0]` and model
access disabled. Baseline registration retrieves it without running the harness.

## Author setup

Install the existing **Yukon Eigen** App on `Layr-Labs/catalyst` for dev:

https://github.com/apps/yukon-eigen/installations/new

Production uses the separate Yukon Autoresearch App. The author also needs
Yukon benchmark-import permission. For a private repo, solvers need ordinary
GitHub read access. No custom Yukon release is needed.

Publish the tested revision to `main`. Record its exact Git SHA and numeric
GitHub repository ID (different from a Yukon benchmark UUID):

```sh
gh api repos/Layr-Labs/catalyst --jq '{id,full_name,default_branch}'
git rev-parse HEAD
```

### Verifier connection

Choose one:

- **HTTPS:** set repository variable `CATALYST_EVALUATOR_URL` to the trusted
  origin with a valid certificate on TCP 443. Keep the internal API on loopback
  port 8778. A stable hostname lets the server move without client changes.
- **SSH:** leave that variable unset. Set repository variables
  `CATALYST_SSH_HOST`, `CATALYST_SSH_USER`, and Actions secrets
  `CATALYST_SSH_KEY`, `CATALYST_SSH_KNOWN_HOSTS`. The workflow establishes a
  private port forward; it still authenticates each lookup with OIDC.

Use a dedicated CI key, never a person's administrative private key. A restricted
OpenSSH authorized-key entry can use:

```text
restrict,port-forwarding,permitopen="127.0.0.1:8778",command="/bin/false" ssh-ed25519 <CI public key>
```

On `openclaw`, the dedicated non-login user is `catalyst-ci`. Its separate SSH
policy in `/etc/ssh/sshd_config.d/90-catalyst-ci.conf` restricts forwarding to
local connections; the authorized-key `permitlisten="none"` option is not valid
on this OpenSSH version:

```text
Match User catalyst-ci
    AllowTcpForwarding local
    AllowStreamLocalForwarding no
    PermitOpen 127.0.0.1:8778
    PermitTTY no
    X11Forwarding no
    ForceCommand /bin/false
Match all
```

Validate with `sshd -t` and check `sshd -T -C user=catalyst-ci,host=localhost,addr=127.0.0.1`
before reloading SSH. The existing administrative user's effective policy must
remain unchanged. This affects SSH transport, not the screen-managed Catalyst API.

Verify the VM host public key through the existing trusted administrative
connection. Never disable host-key checking or trust an unchecked runtime
`ssh-keyscan`. Store the CI key in Actions secrets; keep any local provisioning
copy private and outside Git. The tunnel grants
transport; API authorization separately prevents execution and foreign-result access.

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

For the private VM, keep this connection open in one terminal:

```sh
ssh -N -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:8878:127.0.0.1:8778 openclaw
```

In a separate terminal, using stock Yukon and the registered benchmark name:

```sh
yukon clone bxue-l2/catalyst catalyst-solver
cd catalyst-solver
uv sync --frozen
yukon setup
mkdir -p .catalyst
cp -R harnesses/ecdsa-baseline .catalyst/my-harness
export CATALYST_EVALUATOR_URL=http://127.0.0.1:8878
# Supply your provisioned CATALYST_API_TOKEN privately.
# Set the authorized grant in .catalyst/my-harness/evaluation.json.

uv run catalyst remote submit .catalyst/my-harness --wait
cp .catalyst/my-harness/verification.json submission/verification.json
yukon run
yukon submit --note-file submission-note.md \
  --model "<exact model used, or disabled for this baseline>" \
  --harness "ecdsa-baseline"
yukon submissions --all --json
```

Use an operator-provisioned Catalyst solver key; automatic Yukon login exchange
is not implemented. A model-disabled baseline is not an optimization claim.
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

- The ECDSA MVP has model access disabled. Provider-secret upload/storage/renewal
  is not implemented. Do not send provider secrets to it.
- Missing, foreign or altered receipts, wrong problems/policies, and failed owner
  lookups write no score. The client clears stale score files first.
- Receipt lookup is replay-safe and never enqueues evaluations. Repository
  permissions default to disabled and must be provisioned by an operator.
- This MVP handles initial import and ordinary submissions. Reorgs using separate
  execution IDs need an additional trusted mapping to the original submission;
  unknown IDs fail closed without rerunning a harness.
- A future credential-upload API requires authenticated HTTPS, owner-scoped
  protected storage, expiry, revocation, redaction and scoped worker access.

## Local tests

```sh
uv sync --frozen
uv run python -m unittest discover -s tests
CATALYST_STOCK_YUKON=/path/to/unmodified/yukon \
  uv run python -m unittest discover -s tests -p test_github_receipts.py
```

The optional CLI test needs that checkout's locked dependencies installed. These
fixture tests remain distinct from the live GitHub/App/network checks above.
