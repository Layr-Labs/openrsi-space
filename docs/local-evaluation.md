# Local API, worker and Yukon integration

There are two local modes. The real ECDSA mode runs the pinned challenge through
the API, managed worker, Dungeness/Harbor and independent Rust verifier, with model
access disabled. The small circuit fixture additionally tests model accounting
and the actual Yukon CLI with deterministic model responses. Both use local
authentication; hosted Yukon/OIDC and queued-submission lookup remain fixtures.

## Run the real ECDSA baseline

From the repository root, initialize once:

```sh
.venv/bin/catalyst local-ecdsa-init .catalyst/local-ecdsa \
  --dungeness /Users/bxue/Documents/dungeness-main
```

An existing directory is preserved and cannot be initialized again. Start the
service in one terminal; it starts and supervises the worker automatically:

```sh
.venv/bin/catalyst --state .catalyst/local-ecdsa/service evaluator-serve \
  --local-auth --auth-file .catalyst/local-ecdsa/auth.json \
  --problem-set .catalyst/local-ecdsa/problem-set.json --port 8778
```

In another terminal, configure the client and submit the included harness:

```sh
export CATALYST_EVALUATOR_URL=http://127.0.0.1:8778
unset CATALYST_LOCAL_TEST CATALYST_LOCAL_PROBLEM_SET
export CATALYST_LOCAL_ECDSA=1
export CATALYST_API_TOKEN="$(.venv/bin/python -c \
  'import json; print(json.load(open(".catalyst/local-ecdsa/client-tokens.json"))["solver"])')"

.venv/bin/catalyst --state .catalyst/local-ecdsa/client remote submit \
  harnesses/ecdsa-baseline --wait
```

The harness retains the actual starting `src/point_add` module at
`62ae3d00d1e01d7bc640b5163cfea8dabffd8392`. The worker freezes and hashes its files,
then recompiles and verifies that exact capture in a separate network-disabled
container. Its pinned Dungeness verifier includes the recorded low-memory
streaming backport. First use may download dependencies and build images.

The measured baseline passed all 9,024 shots, with 3,962,753 average Toffoli gates,
2,715 peak qubits and score **10,758,874,395**. Its model credits are **0**.
The configured model and 20-credit ceiling are contract fields; model access is
disabled and attempted requests fail. Evidence is labeled `local-ecdsa`, with
`modelAccess: disabled`; it cannot be relabeled as hosted evidence.

The client saves the judgment and private traces and exports
`harnesses/ecdsa-baseline/verification.json`. Repeating `remote submit` creates a
new evaluation; `remote wait EVALUATION_ID` retrieves an existing one. This is a
real baseline execution, with no model-driven optimization or hosted publication.
See [the harness instructions](../harnesses/ecdsa-baseline/README.md).

## Run the circuit and Yukon integration check

Use Docker Desktop, Bun, the installed Catalyst environment, a clean pinned
Dungeness checkout and a Yukon checkout with its dependencies installed:

```sh
.venv/bin/python scripts/check-local-e2e.py \
  --dungeness /path/to/dungeness \
  --yukon /path/to/yukon
```

`--base-image IMAGE` can select an already cached Python image. Otherwise the
fixture uses `python:3.12-slim-bookworm`. First use can download dependencies and
build Docker images; no provider account or model credit is used.

The script creates a new ignored `.catalyst/local-mvp/<timestamp-id>/` directory
and preserves previous runs. It creates generated fixture Git repositories
without committing or changing the user's checkout. It starts the loopback API,
which launches and supervises its worker, then uses `catalyst remote submit` in a
generated solver workspace. The actual `yukon run` resumes the same accepted request, and
`catalyst remote wait` retrieves it again after completion.
The test manifest differs only in its local Python launch command; the actual
Yukon Pareto parser reads the resulting judgment.

Expected result:

```json
{
  "evidence": "local-test",
  "scores": [3.0, 0.25],
  "jobs": 1,
  "model_requests": 1,
  "workflow_replays": 2,
  "states": ["queued", "building", "running", "verifying", "completed"]
}
```

The harness calls the model through the real gateway and writes the returned
circuit. Its false stdout score of zero is ignored. The trusted verifier checks
all eight input states of the captured circuit in a separate network-disabled
container, returning one Toffoli gate times three qubits. The gateway receipts
contain 20,000 input and 5,000 output tokens, worth 0.25 credits under the pinned
schedule. These are synthetic tokens, not an actual charge.

The check then registers the local submission fixture and invokes the actual
workflow publication client twice. Both requests retrieve the same existing
evaluation. Assertions confirm one job, one model request, one idempotent
publication record, private trace availability and persistent results after
reopening the database. The actual hosted GitHub workflow and hosted Yukon
submission service are not contacted.

## Run the service and client separately

Create a fresh workspace:

```sh
catalyst local-evaluator-init .catalyst/local-manual \
  --dungeness /path/to/dungeness
```

Start the service in one terminal. It automatically starts its worker:

```sh
catalyst --state .catalyst/local-manual/service evaluator-serve \
  --local-test --auth-file .catalyst/local-manual/auth.json \
  --problem-set .catalyst/local-manual/problem-set.json --port 8777
```

The worker configuration defaults to `worker.json` beside the auth file;
`--worker-config PATH` overrides it. The server reports readiness only after the
worker acquires its lock and recovers interrupted jobs. Worker output stays in
the private service state's `worker.log`.

Use a second terminal for submissions, from the repository root:

```sh
export CATALYST_EVALUATOR_URL=http://127.0.0.1:8777
unset CATALYST_LOCAL_ECDSA
export CATALYST_LOCAL_TEST=1
export CATALYST_LOCAL_PROBLEM_SET="$PWD/.catalyst/local-manual/problem-set.json"
export CATALYST_API_TOKEN="$(.venv/bin/python -c \
  'import json; print(json.load(open(".catalyst/local-manual/client-tokens.json"))["solver"])')"

catalyst --state .catalyst/local-manual/client remote submit \
  .catalyst/local-manual/solver/submission --wait
```

Ctrl+C or SIGTERM stops the service and its worker, allowing job cleanup before
forcing termination if necessary. An unexpected worker exit closes the API,
terminates its reported execution process groups and marks interrupted work
failed. Restart the service to continue queued jobs; started evaluations are not
automatically repeated. The standalone `worker` command remains an internal and
development entrypoint; do not start it separately alongside `evaluator-serve`.

This fixture service is restricted to loopback and accepts local-test evidence only. Client
requests require `CATALYST_LOCAL_TEST=1`, a loopback
`CATALYST_EVALUATOR_URL`, `CATALYST_LOCAL_PROBLEM_SET` pointing at the generated
problem set, and the generated solver token in `CATALYST_API_TOKEN` (or
`YUKON_API_TOKEN`). Tokens are
stored only in the private generated `client-tokens.json`; do not copy them into
source or public artifacts. The complete check configures these automatically.

An editable example is available at
[`harnesses/circuit-smoke`](../harnesses/circuit-smoke/README.md). With the same
client environment, submit it using:

```sh
catalyst --state .catalyst/local-manual/client remote submit \
  harnesses/circuit-smoke --wait
```

To exercise that exact harness in the automated check, add
`--harness harnesses/circuit-smoke` to `scripts/check-local-e2e.py`.

The local-only `local-submission-bind` command registers an evaluation against
an owner, repository and commit. It substitutes for a trusted Yukon queue lookup,
not a user-supplied HTTP assertion.

## Persistence, accounting and scope

The API validates source digests, problem/pricing/policy pins and authorized
limits before enqueuing. Retries reuse `(owner, request_id)`; changed payloads
under that key fail. Result and trace reads require the same owner.

A worker lock permits one worker per state directory. Claiming a queued job is
atomic. Restart marks interrupted attempts failed and retains queued work;
started jobs are never automatically replayed. Failures retain private traces.
Dungeness tears down each run's containers; debug artifacts and build images are
retained for development. Neither the API nor worker provisions or removes VMs.

The local worker reconciles gateway receipts with Dungeness terminal accounting
and the local provider's independent counter (zero in model-disabled ECDSA mode).
It freezes the final candidate,
binds independent verification to its digest and seals only eligible terminal
checkpoint windows. Continuous capture across budget boundaries is still
pending. Unmeasured tiers remain metadata, never missing values in Yukon tuples.

This is a local integration milestone. Before hosted use, connect real Yukon
login/OIDC and queued-submission ownership, implement temporary provider access
and renewal for ECDSA research runs, settle checkpoint run
policy, configure service startup at boot and retention on the existing `openclaw`
VM, and register the hosted Yukon benchmark. Real provider credentials and paid
evaluation are unavailable in both current local modes.
