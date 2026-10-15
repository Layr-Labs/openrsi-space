# Existing VM deployment record

**Current integration:** use [GitHub Actions end to end](github-actions-e2e.md).
Release `20261013-generic-runtime-1` is running under `screen` on the existing
VM. It runs arbitrary command harnesses through Dungeness, with model credentials
kept in the gateway. The current provider policy enables `openai-chatgpt` and
`kimi-code`. It includes explicit input-rejection accounting and readable
verifier output for the unprivileged host worker. The previous release and a
database/configuration backup are retained under
`/var/lib/catalyst/evaluator/backups/20261013-generic-runtime-1`.
See [generic harness execution and validation](generic-harnesses.md).

The current release completed a live SkyDiscover/EvoX run using Kimi Code `k3`:
evaluation `0b48d992-00e9-4567-ad47-459767195757`. Ten settled model calls
used 0.685212 normalized credits under a three-credit cap. The agent reached
its 900-second timeout; the independent verifier accepted its retained
baseline candidate. Receipt retrieval through stock `yukon run` passed.
Yukon dev subsequently accepted submission
`22f76880-5436-497d-a403-beab576a4f14` through its hosted GitHub Actions
workflow, with the exact verified pair `[10758874395, 0.000276]`.
The second coordinate is credits at the earliest best observation; the total
run cost remains 0.685212 credits.

Earlier releases completed the hosted Pareto submission flow through stock
`yukon run` and `catalyst yukon-submit`.
Jobs and credentials were preserved, and no evaluation was started by retrieval.
The service is now reachable through **https://35.92.254.142**, with a trusted
IP certificate and tested automatic renewal. Nginx forwards to the existing
loopback API; the API remains screen-managed. See [HTTPS operations](https.md).

Yukon login is active against **https://api-dev.yukon.org**. The generic runtime's
server suite passed 200 tests with eight optional skips. The local dev
login is valid. Legacy Catalyst solver passwords remain disabled.
The starter receipt points to the dev account's original evaluation
`03586584-86c1-4b9d-9a09-1a13701efabe`, with scores `[10758874395, 0]`.

A temporary production login check also completed evaluation
`999da259-c922-444e-9531-0ae070a91037` with the same score and model access disabled.
After the author clarified that the integration targets dev, the operator
reviewed the distinct account IDs, backed up the service, restored the dev issuer
and restarted the API (invalidating existing sessions). Both evaluations and
their original owners remain intact. No evaluation was rerun for this correction.
The issuer audit and pre-change snapshot are under
`/var/lib/catalyst/evaluator/backups/20261007-return-to-dev`.
That historical release's backup is
`/var/lib/catalyst/evaluator/backups/20261007-dev-pipeline-1`.
It enabled solver-selected spending caps above the $20/$200 comparison
checkpoints while still using a model-disabled runtime policy. HTTPS receipt
retrieval passed after that release switch without creating another evaluation.
The current release enables metered model access as described above.

The details below record **earlier deployments and the direct-backend prototype**, including its
historical release and tests. Do not apply the custom Yukon provider or follow
its registration steps for the GitHub Actions integration.

Catalyst is installed on the existing `openclaw` VM. The API supervises its
worker; harnesses and independent verification run in Docker on that same VM.
The current service executes real pinned ECDSA candidates with **model access
disabled**. No provider subscription or API credential is installed.

Verified remote evaluation: `03586584-86c1-4b9d-9a09-1a13701efabe`, with Pareto
scores `[10758874395, 0]`. The new Yukon provider retrieved its baseline and
submission judgments, repeated retrieval without another evaluation, and
rejected a different owner. The result remained retrievable after restarting
the screen-managed service. Two earlier failed attempts remain recorded.
The service now runs `catalyst-yukon-v2` from release
`20261007-receipt-only-1`. Receipt-only retrieval passed against that same
evaluation. The real Yukon CLI, local API, PostgreSQL queue and worker also
completed a submission and returned `[10758874395, 0]` through Yukon's HTTP API.
A repeated submission reused the same Yukon record with no new validation job.

The local Yukon/Catalyst code has since moved to the project-independent
`yukon-remote-verification-v1` contract at `POST /yukon/v1/retrieve`.
That change has **not been deployed** to this VM. The current Yukon checkout
requires the generic endpoint; upgrade the Catalyst release before repeating
the integration commands below with the new provider. The existing receipt
remains usable without rerunning the harness. The old endpoint is retained in
the new Catalyst source for previously deployed consumers, subject to the new
explicit consumer benchmark grants.
See [the shared contract](remote-evaluation.md#receipt-only-yukon-submission).

## Benchmark authorization

The updated code denies remote retrieval by default. The manifest's runner
selection alone does not enable it. For an operator-reviewed benchmark UUID, add
the following entry to the Yukon service's private `benchmarks` map and to the
matching consumer token principal's `benchmarks` map in Catalyst's private
`auth.json`:

```json
{
  "<benchmark UUID>": {
    "enabled": true,
    "problem": {"id": "ecdsa.fail", "version": "<pinned problem-set SHA-256>"}
  }
}
```

Use the reviewed problem definition to obtain the version, not solver input:

```sh
.venv/bin/python -c 'from catalyst.problems import initial_problems; from catalyst.remote import digest; print(digest(initial_problems()))'
```

The consumer token stays secret; only its hashed-token principal is edited on
the Catalyst service. Restart/reload both services after changing their private
configuration. Disabling the entry prevents further retrieval after reload.
`initialize-remote` creates an empty consumer allowlist; it grants no benchmarks.
Both the generic and compatibility endpoint require the scoped grant.

For a new benchmark, hold its baseline job while importing to obtain its Yukon
UUID, then provision both explicit grants and start the worker. The local
launcher handles this by leaving the new benchmark queued and printing its UUID
before starting a worker. It never enables remote verification automatically.
An existing receipt can be reused: no new model run is required.

## Start and stop

The service runs in a detached `screen` session under the dedicated `catalyst`
account. It does not require a Catalyst systemd service. Start it on the VM:

```sh
sudo -u catalyst screen -dmS catalyst -L \
  -Logfile /var/lib/catalyst/evaluator/service/screen.log \
  /bin/sh /opt/catalyst/current/scripts/run-remote-service.sh
```

Inspect or attach:

```sh
sudo -u catalyst screen -ls
sudo -u catalyst screen -r catalyst
```

Detach with **Ctrl+A, D**. Stop with **Ctrl+C** while attached; the API stops its
worker and owned execution processes. Interrupted jobs are marked failed and
are never automatically rerun. Start the screen session again after a VM reboot.
Docker's normal daemon remains managed by the operating system.

The launcher sets the file mask to `022` so runtime files copied into container
images are readable by non-root users. State roots are private (`0700`);
credentials, worker logs and trace archives have explicit private permissions.

## Submit from your Mac

After enabling Yukon authentication, use HTTPS and the existing Yukon login:

```sh
cd /Users/bxue/Documents/catalyst
export CATALYST_EVALUATOR_URL=https://35.92.254.142
export YUKON_API_URL=https://api-dev.yukon.org
unset CATALYST_API_TOKEN CATALYST_LOCAL_TEST CATALYST_LOCAL_ECDSA CATALYST_LOCAL_PROBLEM_SET
# Existing Yukon login, or YUKON_API_TOKEN supplied privately.

.venv/bin/catalyst --state .catalyst/remote-vm/client remote submit \
  harnesses/ecdsa-baseline --wait
```

Every completed `submit` followed by another `submit` creates a new evaluation.
Use `remote status ID` or `remote wait ID` to retrieve the existing attempt.
No Catalyst solver credential needs to be downloaded or saved.

Enable login on a new service (operator command, no user key needed):

```sh
sudo -u catalyst /opt/catalyst/current/.venv/bin/catalyst yukon-auth-configure \
  --auth-file /var/lib/catalyst/evaluator/auth.json \
  --worker-config /var/lib/catalyst/evaluator/worker.json \
  --yukon-api https://api-dev.yukon.org
```

Use the same trusted Yukon instance as the challenge, then restart the
screen-managed API. This disables old solver passwords, preserves consumer and
GitHub authorization, and enables bounded model-disabled runs for valid Yukon
users. See [the authentication contract](remote-evaluation.md#yukon-authentication).

## Server state

- Releases: `/opt/catalyst/releases/`; active release: `/opt/catalyst/current`.
- Pinned Dungeness: `/opt/catalyst/dungeness`.
- Configuration and credential hashes: `/var/lib/catalyst/evaluator/`.
- Durable queue/results: `/var/lib/catalyst/evaluator/service/jobs.sqlite`.
- Private artifacts: `/var/lib/catalyst/evaluator/service/artifacts/<evaluation_id>/`.
- Dungeness runs/builds: `/var/lib/catalyst/evaluator/worker/`.
- Worker log: `/var/lib/catalyst/evaluator/service/worker.log`.

The API binds only to VM loopback; Nginx provides public HTTPS. Solver identity
comes from Yukon's `/api/me`, with memory-only, 15-minute sessions that the client
renews automatically. Raw Yukon keys never enter jobs, logs or retained artifacts.
The launcher disables core dumps; this VM has no enabled swap. The legacy Yukon
consumer key can retrieve authorized public judgments but cannot enqueue
evaluations or download private traces. GitHub OIDC remains independent.

## Historical direct-runner prototype (unused)

The following describes the earlier local prototype. It is not the hosted
integration and must not be deployed for the current GitHub Actions workflow.

The obsolete direct-runner prototype patches are no longer distributed.
Use [GitHub Actions end to end](github-actions-e2e.md) for the supported
integration; the description below is historical only.

The manifest uses:

```json
{
  "mode": "pareto",
  "promotionMode": "automatic",
  "runner": {
    "provider": "remote-verification",
    "service": "catalyst",
    "receiptPath": "submission/verification.json"
  }
}
```

Both objectives minimize: verified `avg_toffoli × peak_qubits`, and model credits
at that capture. Tier summaries and complete curves remain in public metrics.

`yukon submit` uploads only the receipt file. The Yukon backend loads the pinned
benchmark's retrieval configuration and reads that receipt from the bounded
submission archive. It sends the evaluation ID, stored solver account ID,
benchmark/submission IDs, receipt and requested Pareto fields to:

```text
POST /evaluations/<evaluation_id>/yukon
```

Catalyst checks ownership and the receipt's bindings against its stored evaluation,
records an immutable Yukon submission binding, and returns a public judgment.
Yukon validates the finite Pareto tuple using its existing parser. The provider
does not run setup/benchmark commands or launch another harness evaluation.
Harness source and evaluation settings are already stored in Catalyst and are
not uploaded to Yukon. Baseline import likewise requires an existing verified reference in the
benchmark's starter submission. Promotion is a separate reviewed source change.

Deployment configuration lives in a private file selected by
`YUKON_REMOTE_VERIFIERS_FILE`, not in the benchmark manifest:

```json
{
  "catalyst": {
    "url": "http://127.0.0.1:8878",
    "token": "<dedicated Yukon consumer token>",
    "baselineOwnerId": "<Yukon account UUID>"
  }
}
```

The destination is operator-configured; submissions cannot choose another URL.
HTTPS is supported, and plain HTTP is limited to loopback for private tunnels.
The backend deployment needs its own secure route to the VM. A tunnel on your
Mac does not make the endpoint reachable from the hosted Yukon backend.

To exercise the actual new Yukon provider against an already completed remote
evaluation, prepare a local benchmark workspace containing this manifest and
the remote receipt at `submission/verification.json`. This requires a service
running the current v2 retrieval protocol:

```sh
cd /Users/bxue/Documents/yukon/yukon
YUKON_REMOTE_VERIFIERS_FILE=/Users/bxue/Documents/catalyst/.catalyst/remote-vm/yukon-verifiers.json \
  bun scripts/check-remote-verification.ts \
  /Users/bxue/Documents/catalyst/.catalyst/remote-vm/yukon-receipt-workspace \
  /Users/bxue/Documents/catalyst/.catalyst/remote-vm/yukon-retrieval.json \
  "<authorized-test-benchmark-uuid>" "<pinned-benchmark-revision>"
```

This uploads only the receipt and checks baseline retrieval, submission retrieval, replay consistency and
cross-owner rejection. It does not publish to Yukon or push source.

For the full local Yukon API/worker/database flow, use the two separate commands
in Yukon's `docs/catalyst-receipt-local.md`: `catalyst-local-api.ts` starts the
local service and `check-catalyst-local.ts` submits through the actual CLI.
Local state lives in `.catalyst/yukon-local/`. This exercises the normal queue and
Pareto persistence path without contacting the hosted Yukon API.

The hosted Yukon API/CLI must receive these changes, have a secure connection
and service credential configured, and register the benchmark before live
`yukon submit` works. The current deployment does not change hosted Yukon.
