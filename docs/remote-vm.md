# Existing VM deployment record

**Current integration:** use [GitHub Actions end to end](github-actions-e2e.md).
Release `20261007-github-actions-1` is now running under `screen` on the existing
VM. Stock `yukon run` retrieved the real receipt through its new endpoint.
Jobs and credentials were preserved, and no evaluation was started by retrieval.

The details below record the **earlier direct-backend prototype**, including its
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

Keep a private tunnel open in one terminal:

```sh
ssh -N -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:8878:127.0.0.1:8778 openclaw
```

In another terminal:

```sh
cd /Users/bxue/Documents/catalyst
export CATALYST_EVALUATOR_URL=http://127.0.0.1:8878
unset CATALYST_LOCAL_TEST CATALYST_LOCAL_ECDSA CATALYST_LOCAL_PROBLEM_SET
export CATALYST_API_TOKEN="$(.venv/bin/python -c \
  'import json; print(json.load(open(".catalyst/remote-vm/client-tokens.json"))["solver"])')"

.venv/bin/catalyst --state .catalyst/remote-vm/client remote submit \
  harnesses/ecdsa-baseline --wait
```

Every completed `submit` followed by another `submit` creates a new evaluation.
Use `remote status ID` or `remote wait ID` to retrieve the existing attempt.
Credentials downloaded during deployment are in ignored, private local files.

## Server state

- Releases: `/opt/catalyst/releases/`; active release: `/opt/catalyst/current`.
- Pinned Dungeness: `/opt/catalyst/dungeness`.
- Configuration and credential hashes: `/var/lib/catalyst/evaluator/`.
- Durable queue/results: `/var/lib/catalyst/evaluator/service/jobs.sqlite`.
- Private artifacts: `/var/lib/catalyst/evaluator/service/artifacts/<evaluation_id>/`.
- Dungeness runs/builds: `/var/lib/catalyst/evaluator/worker/`.
- Worker log: `/var/lib/catalyst/evaluator/service/worker.log`.

The API binds only to VM loopback. SSH provides transport authentication and
encryption; API bearer keys separately control solver and Yukon access.
The solver key is bound to the verified Yukon account ID. The dedicated Yukon
consumer key can retrieve public judgments but cannot enqueue evaluations or
download private traces. This is explicit account provisioning, not automatic
Yukon login/token validation. Automatic grant issuance and renewal remain future
work.

## Yukon changes

The implementation is applied to `/Users/bxue/Documents/yukon/yukon`.
The exportable patch and base revision are under
`integrations/yukon/`. The prior UI preview is preserved separately.

The manifest uses:

```json
{
  "mode": "pareto",
  "promotionMode": "manual",
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
