# Remote VM and Yukon Pareto integration

Catalyst is installed on the existing `openclaw` VM. The API supervises its
worker; harnesses and independent verification run in Docker on that same VM.
The current service executes real pinned ECDSA candidates with **model access
disabled**. No provider subscription or API credential is installed.

Verified remote evaluation: `03586584-86c1-4b9d-9a09-1a13701efabe`, with Pareto
scores `[10758874395, 0]`. The new Yukon provider retrieved its baseline and
submission judgments, repeated retrieval without another evaluation, and
rejected a different owner. The result remained retrievable after restarting
the screen-managed service. Two earlier failed attempts remain recorded.

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

The implementation checkout is `.catalyst/yukon-remote-service`, based on the
existing Yukon checkout. The exportable patch and base revision are under
`integrations/yukon/`. The prior UI preview is preserved separately.

The manifest uses:

```json
{
  "mode": "pareto",
  "promotionMode": "manual",
  "runner": {
    "provider": "remote-verification",
    "service": "catalyst",
    "submissionPath": "submission"
  }
}
```

Both objectives minimize: verified `avg_toffoli × peak_qubits`, and model credits
at that capture. Tier summaries and complete curves remain in public metrics.

The Yukon backend materializes the pinned benchmark, safely applies the
submission archive, computes the submitted file hashes and reads its
`verification.json`. It sends the evaluation ID, the stored solver account ID,
source hashes, configuration, reference and requested Pareto fields to:

```text
POST /evaluations/<evaluation_id>/yukon
```

Catalyst checks ownership and every binding against the stored evaluation,
records an immutable Yukon submission binding, and returns a public judgment.
Yukon validates the finite Pareto tuple using its existing parser. The provider
does not run setup/benchmark commands or launch another harness evaluation.
Baseline import likewise requires an existing verified reference in the
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
the matching `submission/` source, configuration and remote reference:

```sh
cd .catalyst/yukon-remote-service
YUKON_REMOTE_VERIFIERS_FILE=/Users/bxue/Documents/catalyst/.catalyst/remote-vm/yukon-verifiers.json \
  bun scripts/check-remote-verification.ts \
  /Users/bxue/Documents/catalyst/.catalyst/remote-vm/yukon-workspace \
  /Users/bxue/Documents/catalyst/.catalyst/remote-vm/yukon-retrieval.json
```

This checks baseline retrieval, submission retrieval, replay consistency and
cross-owner rejection. It does not publish to Yukon or push source.

The hosted Yukon API/CLI must receive these changes, have a secure connection
and service credential configured, and register the benchmark before live
`yukon submit` works. The current deployment does not change hosted Yukon.
