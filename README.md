# Catalyst

Catalyst evaluates autonomous research harnesses on **ecdsa.fail**. Solvers
submit harness source; Catalyst builds and runs it under controlled conditions,
meters model use, and independently verifies candidate circuits.

Compare harnesses at **$20 and $200 in model credits, plus Best achieved**. At each tier,
rank the best eligible verified `avg_toffoli × peak_qubits`; lower is better.
Best achieved considers the full verified run without a fixed comparison budget
and displays credits consumed at that candidate. Every run still has an explicit
finite spending cap; there is no $2,000 comparison tier.
Keep the complete performance–cost curve and every attempt, including failures
and regressions. Infrastructure costs are accounted for separately.

Model credits retain existing immutable reference rates in
[`pricing.json`](src/catalyst/problem-set/pricing.json).
The service resolves additional declared models through a
[service-issued OpenRouter pricing snapshot](docs/generic-harnesses.md#reference-prices-for-declared-models).
The exact schedule's content hash is bound into every evaluation and
verification reference. These are comparison rates. Subscription usage can consume account
allowance without representing a cash charge. Unknown usage or unpriced models
cannot establish tier eligibility.

Each evaluation runs under the solver's chosen spending cap. **Within $20**,
**Within $200**, and **Best overall** are display views over the saved curve;
a $5 run qualifies for both budget views. Changing the view never starts a run.
Catalyst exports the existing Dungeness evaluator history and settled usage.

See [budget accounting](docs/tier-accounting.md) for exact eligibility and
[the challenge UI](docs/challenge-ui.md) for the local preview and Yukon handoff.

## Solver workflow

First-time users: see [which token to use and how to sign in](docs/live-models.md#which-token-and-where-does-it-come-from).
Yukon login, temporary model access and the returned verification receipt are
three different things; the CLI handles model-token extraction and receipt creation.
For your own agent, including its knowledge base and dependencies, see the
[general source submission flow](docs/generic-harnesses.md#submit-your-own-agent).
The CLI accepts per-run `--provider`, `--model` and `--budget` options,
and `--entrypoint` lets an existing repository run without `harness.json`;
generic remote execution is deployed on the existing VM.

The root [`benchmark.json`](benchmark.json) is one schema-v1 Yukon benchmark,
using stock Yukon's GitHub Actions runner. Only `submission/verification.json`
is submitted to Yukon:

```sh
yukon setup
mkdir -p .catalyst
cp -R harnesses/ecdsa-baseline .catalyst/my-harness
# Develop the harness and configure its evaluation.json and authorized access grant.
uv run catalyst remote submit .catalyst/my-harness --wait
cp .catalyst/my-harness/verification.json submission/verification.json
yukon run     # preview the existing receipt; never starts an evaluation
uv run catalyst yukon-submit --no-dependencies --note-file submission-note.md \
  --model "<exact model>" --harness "<harness>"
```

No Yukon code changes or custom runner are required. `catalyst yukon-submit`
calls stock `yukon submit`, then authenticates its job mapping with the verifier.
Yukon's Pareto workflow branch uses an execution UUID distinct from the submission
UUID, so plain `yukon submit` alone does not complete this mapping. Use
`--dependencies-file` instead of `--no-dependencies` when reusing an earlier submission.
`yukon setup` downloads the pinned ECDSA workspace and local verifier. Develop
and check candidates in that existing workspace, retaining context and build
caches. Improve the autonomous harness's code, tools, instructions and knowledge
under the ignored `.catalyst/my-harness/` directory. Local tests provide development feedback.

Select a supported provider/model, private access-grant reference, and an explicit model-credit cap in the harness's `evaluation.json`. Its token and wall-time
limits are additional safety caps; they do not promise that the entire credit
allowance will be consumed. The starter uses a 20-credit cap, 100,000 tokens and
900 seconds; its grant reference is deliberately blank.

The local worker builds immutable source, starts from the pinned problem state,
captures the final candidate and independently verifies it. Real ECDSA execution
is available with model access disabled or through an operator-enabled
[temporary ChatGPT access](docs/live-models.md) uses native Codex through Dungeness; the challenge adapter exports its existing evaluator history. Local interactive state is not an
implicit input. The required repetition policy
remains undecided; preserve attempts and show counts rather than hiding repeats.

The client downloads private traces and writes `verification.json` in the harness
directory. Copy that receipt into `submission/verification.json`.
For complete source and recorded run evidence, use
[`catalyst remote download`](docs/artifact-sharing.md). Harness source and
sanitized traces can be published separately by their owner; both remain
private by default.
The helper's stock `yukon submit` call uploads only that receipt.
Yukon creates the candidate commit and dispatches the repository's workflow. That
workflow authenticates with GitHub OIDC and retrieves the existing evaluation.
Catalyst registers the execution/submission mapping through Yukon's authenticated
job API, using the solver's key transiently without retaining it. It resolves the
solver account through Yukon's existing submission API and checks the
receipt's source, image, problem, configuration, pricing and policy identities
against its retained evaluation. The harness was uploaded to Catalyst during
`catalyst remote submit` and stays in Catalyst's evidence store.
Retrieval does not purchase a second run.
A local score or reference file is not proof of remote verification.
Editing local harness files after a run does not change what its receipt refers
to; submit a new evaluation to score those edits.

## Direct verification-service CLI

Use Catalyst directly while developing the service:

```sh
catalyst remote submit submission             # enqueue and return an evaluation ID
catalyst remote status EVALUATION_ID
catalyst remote wait EVALUATION_ID            # retrieve and validate that same run
catalyst remote traces EVALUATION_ID
```

Or submit and wait in one command: `catalyst remote submit submission --wait`.
Configure `CATALYST_EVALUATOR_URL=https://3.21.93.126` and use your existing
Yukon login or `YUKON_API_TOKEN`. No separate Catalyst password is needed.
Catalyst validates the key with its configured Yukon API and returns a 15-minute
solver session, renewed automatically by the client. Keys and sessions are never
saved by the server. `CATALYST_API_TOKEN` remains for local test fixtures only.
Provider access is separate. Live runs use the
[Codex credential handoff](docs/live-models.md) after operator enablement.

Yukon login, native Codex access, intermediate history and candidate screening are
live in release `20261008-history-screen-1`, configured against
**https://api-dev.yukon.org**. This integration targets **dev Yukon**, using the
Yukon Eigen GitHub App and a dev API key. Keys from `www.yukon.org` belong to
production and cannot authenticate here.

The remote client uses `.catalyst/remote/` state. Resume interrupted waiting with
`catalyst remote wait EVALUATION_ID`. Once it finishes, copy the returned receipt
into `submission/verification.json`. `yukon run` only checks that receipt.
A subsequent `submit` after completion deliberately requests a fresh evaluation;
`status`, `wait` and `traces` never enqueue work.

See [the client contract](docs/remote-evaluation.md#standalone-client),
[the local service setup](docs/local-evaluation.md), and
[the deployed VM commands](docs/remote-vm.md). The private service runs on the
dedicated `catalyst-prod` VM, reached through HTTPS, with temporary provider access.
Existing evaluations and receipt identities have been copied from Openclaw.
This endpoint still authenticates against Yukon dev; see
[the verifier endpoint](docs/verifier-endpoint.md).

The real Codex/Astra/high test completed at **0.887796 model credits** and
independently verified **10,704,574,395** (3,942,753 average Toffoli gates ×
2,715 peak qubits), a 0.505% improvement over the pinned baseline. Its receipt
was retrieved through the HTTPS client and the hosted Yukon workflow. The latest
test retained six verified observations and completed the same hosted flow, at
2.720172 credits total across a rejected token-limit attempt and its corrected
replacement. See [live end-to-end evidence](docs/github-actions-e2e.md).

For the actual pinned ECDSA problem, use
[`harnesses/ecdsa-baseline`](harnesses/ecdsa-baseline/README.md). The submitted
harness retains the starting Rust module, runs through Dungeness, and receives
fresh independent verification. This mode disables model requests and uses local
authentication. The verified baseline scored **10,758,874,395**
(3,962,753 average Toffoli gates × 2,715 peak qubits), with all 9,024 shots passing
and zero model credits. It establishes an executable baseline, not an optimization.

An editable harness for that local service is included at
[`harnesses/circuit-smoke`](harnesses/circuit-smoke/README.md). Submit it with
`catalyst remote submit harnesses/circuit-smoke --wait` after configuring the
local client. It makes a model request through Dungeness and writes a candidate
that the worker independently verifies.

## Implementation and hosting boundary

Implemented locally:

- Pinned ECDSA downloads and local verification commands.
- Executable source packaging, Docker builds, offline smoke tests, and a
  Dungeness/Harbor adapter.
- Local catalog and a checkpoint and best-result viewer using explicitly synthetic or
  contributor-reported observations. Its rankings illustrate the policy;
  local records do not establish official checkpoint eligibility.
- Reference credit calculation, trusted-result validation, budget views,
  full verified curves, and the remote client/submission HTTP contract.
- A Pareto Yukon manifest and a receipt-only GitHub Actions judge using stock
  Yukon dispatch and score artifacts. GitHub OIDC authentication binds the repository,
  workflow, source commit and submission owner before releasing results.
- A loopback verification API with a durable SQLite queue, owner authorization,
  idempotent requests and publication, and a separate Dungeness/Docker worker.
  The real ECDSA baseline uses local identities and disables model access; the
  small circuit integration fixture uses a mock model provider.
  `evaluator-serve` starts and supervises the worker automatically; one terminal
  runs the service and a second submits evaluations. Ctrl+C stops both processes.

The [local integration check](docs/local-evaluation.md) runs the actual Yukon CLI,
API, worker, gateway accounting and independent circuit verifier. It also checks
that workflow publication reuses the completed job. Only external identity,
submission registration and model responses are fixtures; its tiny circuit is
explicitly labeled local-test evidence and cannot count as an ECDSA result.

Remote Codex/ChatGPT and SkyDiscover/EvoX with Kimi K3 runs have completed
independent verification and the stock Yukon dev receipt workflow.
The benchmark is `layr-labs/catalyst` in Pareto mode. The UI, existing-history
export and deterministic cheat screening are implemented. History export and
screening are running on the VM, together with private artifact downloads and
opt-in source/trace publication. The challenge UI's score matrix and artifact
disclosures are maintained in the isolated Yukon branch and are not yet hosted.
Artifact storage currently uses the VM; S3 activation is deferred.
Renewal and user cancellation remain separate work.

Develop and test on the Mac first. The initial remote MVP hosts the API and runs
the harness worker inside the existing VM accessible through `ssh openclaw`.
Reuse that VM across jobs; there is no per-evaluation VM provisioning or teardown.
Use separate run workspaces/containers for builds, harness execution and candidate
verification, keeping the API process outside submitted code's access. Agent Compose and new cloud resources are unnecessary for the MVP.

The optional live-model service receives temporary ChatGPT access over authenticated
HTTPS on port 443. Renewable credentials remain on the client. API memory, a private
worker socket and Linux tmpfs carry temporary access into native Codex; credentials
are excluded from persisted jobs, source packages and receipts. Native subscription
mode exposes temporary access to the harness container. Dungeness supplies usage
accounting and budget enforcement. See [live-model operation](docs/live-models.md)
for cleanup, budget-boundary behavior and current limitations.

See [architecture](docs/architecture.md), [runtime requirements](docs/runtime-platform-requirements.md),
[remote evaluation](docs/remote-evaluation.md), and [executable development](docs/executable-harness.md).
For the complete GitHub/Yukon setup and solver commands, use
[the end-to-end guide](docs/github-actions-e2e.md).
The existing VM now exposes the authenticated API at **https://35.92.254.142**;
see [HTTPS operations](docs/https.md) for certificate renewal and client setup.

## Yukon compatibility

Yukon score tuples require finite values for every objective. Catalyst emits
`[best_verified_performance, model_credits_at_that_capture]` with two minimizing objectives.
The second value is the cumulative model credits at the best candidate.
The authorized cap and total run usage are recorded separately. Per-tier eligibility,
actual usage and the full curve remain in metrics; unmeasured tiers have explicit
states and no fabricated score. This Pareto transport is not the tier leaderboard:
Catalyst's board must rank eligible results separately at the selected tier.

Keep one shared submission path. Separate budget tiers must not become Yukon
tracks over the same editable files. The new challenge board uses stock Yukon responses; see
[the UI handoff](docs/challenge-ui.md).

## Try the viewer

Requires `uv` and Python 3.11+. Install the project and its locked dependencies:

```sh
uv sync
```

Run from this checkout:

```sh
uv run catalyst demo
uv run catalyst serve
```

Open **http://127.0.0.1:8765**. The demo is explicitly synthetic and makes no
model calls. Select $20, $200 or Best achieved to see the synthetic ECDSA ordering
change. The full curves remain visible at every tier.

`uv` manages `.venv` automatically; activation is unnecessary.
All commands accept `--state DIRECTORY` before the subcommand;
the default state directory is `.catalyst` in the current working directory.
`CATALYST_STATE` also selects it.

The server binds only to localhost. This is a single-user prototype, without
accounts, permissions, billing, or remote execution workers.

## Pin Dungeness

```sh
uv run catalyst init --dungeness /Users/bxue/Documents/dungeness-main
```

Catalyst records the checkout's exact commit. A moved or dirty checkout is
rejected until you deliberately update the pin with `init`.

For each evaluation, Catalyst creates an isolated dependency checkout of that
commit, stages the frozen research inputs, records them in a local runtime
commit, and invokes the Dungeness CLI. Executable runs apply the reviewed
[generic command interface patch](src/catalyst/runtime/dungeness-command.patch)
when the upstream pin does not already provide that interface.
The original checkout remains unchanged. Both the upstream commit and the
execution-input commit are recorded.

The isolated checkout shares Git objects with the configured installation.
Keep that installation available while retaining evaluations. Each checkout
currently materializes the upstream files, so disk use depends on Dungeness's
size. Storage optimization is intentionally deferred.

## Create a problem

Start with an editable example:

```sh
uv run catalyst problem create square --title "Integer square"
```

This creates:

```text
problems/square/
  problem.json       identity, metric, direction, and execution configuration
  instructions.md    problem statement
  source/            example candidate and a local checker
  verifier/          independent verifier image and grading scripts
```

Replace the example with your research question and its evaluation criteria.
Keep `verifier/grade.py` synchronized with those criteria. The local checker
is an authoring helper; the verifier defines the reported metric.

**Current Dungeness constraint:** an evaluation starts from a full source commit
in an HTTPS Git repository. Commit your candidate/environment source and set
`execution.repository.url` and `execution.repository.commit` in `problem.json`.
You can supply these through `problem create --repository URL --commit SHA`.
The actual candidate workspace comes from that pinned repository, not from
uncommitted edits in `source/`. Local source execution without this repository
binding is not implemented.

For an existing Dungeness problem, reuse its task/checkpoint binding:

```sh
uv run catalyst problem create point-add \
  --task task:users/bx/ecdsa-fail-v2 \
  --checkpoint checkpoint:public/github/layr-labs/ecdsafail-challenge/62ae3d00d1e01d7bc640b5163cfea8dabffd8392
```

This copies the task's statement and metric into the authored package. The
execution adapter resolves its environment and verifier from the pinned
Dungeness checkout. Changing the statement alone does not change the verifier.

## Capture insights in a harness

```sh
uv run catalyst harness create notes \
  --agent agent:projects/dungeness/codex-openai
```

Edit `harnesses/notes/instructions.md` and add reusable material under
`harnesses/notes/knowledge/`. Declare the intended scope and any problem-specific
tuning in `harness.json`. Supported Dungeness `agent_options` can be included
there. No Dungeness code change is needed for ordinary instructions or knowledge.

To derive a method with attribution:

```sh
uv run catalyst harness create improved --from harnesses/notes
```

The new manifest retains the exact source harness ID and snapshot hash.
Executable packages use the new generic adapter rather than requiring a new
host integration per submitted runtime. The
[generic harness implementation](docs/generic-harnesses.md) supports multiple
models and gateway-owned credentials, with a two-process Python example in
`harnesses/ecdsa-ensemble`. The deployed runtime has also completed a live
EvoX/Kimi run and hosted Yukon receipt validation.
See [the executable contract](docs/executable-harness.md).

## Evaluate and continue locally

These standalone Dungeness tools retain arbitrary development budgets. Their
records are contributor-reported and cannot qualify for official tiers. Official
Yukon evaluations require an explicit credit cap and trusted accounting.

First inspect a prepared evaluation without starting Docker or making model calls:

```sh
uv run catalyst evaluate problems/point-add harnesses/notes \
  --budget 1 --max-tokens 100000 --prepare-only
```

The command prints an evaluation ID and generated run specification. Then:

```sh
uv run catalyst evaluation show EVALUATION_ID
uv run catalyst evaluation execute EVALUATION_ID
```

Omit `--prepare-only` to execute immediately. Execution uses Dungeness's
prerequisites and authentication. Its default credential-file path is the
configured original checkout's `.env`; `--env-file PATH` can select another.
Credential-file contents are never packaged.

Continuation is optional for controlled evaluations:

```sh
uv run catalyst evaluate problems/point-add harnesses/notes \
  --budget 1 --resume EVALUATION_ID
```

The budget is the new attempt's allowance. Comparison costs include known
ancestor model spend. Dungeness retains its own candidate compatibility checks.

To import an existing canonical Dungeness record:

```sh
uv run catalyst import-run /path/to/run/record.json \
  --problem problems/point-add --harness harnesses/notes --id imported-attempt
```

Imported package associations are explicitly contributor-declared, not proof
that those packages were used. Imported continuations require
`--starting-cost USD` for budget comparison; without known ancestry they remain
visible but unranked.

## Publish, obtain, and report

Publication is explicit. The following adds the evaluation's frozen problem,
harness, and normalized result to the local catalog:

```sh
uv run catalyst evaluation publish EVALUATION_ID
```

You can publish authored packages independently:

```sh
uv run catalyst publish problems/point-add
uv run catalyst publish harnesses/notes
uv run catalyst publish .catalyst/runs/imported-attempt
uv run catalyst list
```

Referenced problem/harness versions must be published before a run. Import
snapshots are preserved under `.catalyst/imports/ID/`; `publish` also accepts
their ZIP files if the original package has since changed.

Raw records and model/web traces can contain research contents. They are omitted
from run publications by default. Add `--include-trace` to deliberately include
available raw evidence, subject to the prototype's 64 MiB bundle limit. Make this
choice on the first publication; a published run cannot be changed later.

Obtain an exact published version:

```sh
uv run catalyst fetch harness notes FULL_VERSION_HASH --output harnesses/obtained
```

`publish`, `fetch`, `report`, and `evaluation publish` accept `--server URL` to
use the same local catalog service through HTTP instead of direct storage.
This interface is not an authenticated public hosting solution.

Reports preserve evidence concerns without automatically declaring overfitting:

```sh
uv run catalyst report RUN_ID RUN_VERSION_HASH \
  --body "Describe the reproduction or transfer failure and its conditions." \
  --supporting-run ANOTHER_RUN_REFERENCE
```

## Comparison rules

Official tier rules are defined in [tier accounting](docs/tier-accounting.md).
The local catalog compares one exact problem version, model and condition group.
It shows the best reported result within the selected tier, its actual cumulative
model credits, the attempt range/counts, and complete individual curves.
Known continuation ancestry is included; unknown costs stay unranked. No
interpolation or future candidate can improve an earlier tier. Imported local
records lack official capture seals and must remain contributor-reported.

Published runs are immutable. Duplicated source records do not count as
independent repetitions. Local Pareto highlights show observed score/cost
tradeoffs; they do not certify official remote execution or generalization.

## Development and validation

```sh
uv run python -m unittest discover -s tests -v
node --check src/catalyst/static/app.js
```

An optional offline check runs the actual Dungeness manifest validators and
compiler with fixture repository checkouts:

```sh
CATALYST_DUNGENESS=/path/to/dungeness \
  uv run python -m unittest discover -s tests -p test_dungeness_contract.py -v
```

It does not start Docker or call model providers. A paid live-agent run is a
separate check.

The implementation uses Python, SQLite, and plain HTML/CSS/JavaScript. Immutable
ZIP bundles hold the published content; SQLite indexes them. The small
`src/catalyst/dungeness.py` adapter is the boundary to the execution framework.
Background mockups and the archived Yukon preview are historical design artifacts;
the current contracts above define the ECDSA-only challenge.
