# Local checks before a remote run

Test locally with Dungeness before recommending a remote submission. It is the
public execution backend that coordinates the harness, model gateway, problem
service and evaluator in Docker. OpenRSI prepares and starts these components.
See [the architecture](architecture.md) for how local tests, official evaluations
and Yukon publication fit together.

Use packaging and synthetic checks first, then a model-enabled integration run.
Preparation alone is not a complete test. If local execution is blocked or declined,
report that explicitly before proceeding remotely. The CLI checks existing local
records before submission. Funded admission requires a matching private evidence
bundle whose recorded local cap covers the requested remote cap. Actual spending
may be lower; the local check cannot be skipped. See [funded requirements](platform-funded-inference.md).
Neither local scores nor successful tests guarantee a receipt.

## Check a candidate circuit

```sh
openrsi-space problem clone ecdsa.fail .openrsi/ecdsa-workspace
openrsi-space problem setup ecdsa.fail --workspace .openrsi/ecdsa-workspace
openrsi-space problem check ecdsa.fail --workspace .openrsi/ecdsa-workspace
```

The clone is pinned. Edit only the allowed candidate paths. These commands use
the upstream verifier on your machine; setup can download dependencies. They do
not run a research agent, isolate all networking or meter model usage, and their
scores are not official remote evidence.

These verifier-only commands clone the historical upstream implementation.
They do not assemble the blank research scaffold or its neutral SDK. To test
the actual default starting workspace, including a candidate using
`crate::point_add_sdk`, use the full Dungeness path below.

## Check harness packaging and its entrypoint

```sh
openrsi-space harness create my-agent --executable --output .openrsi/my-agent
openrsi-space harness build .openrsi/my-agent
openrsi-space harness smoke BUILD_ID --workspace .openrsi/ecdsa-workspace --problem ecdsa.fail
```

Replace `BUILD_ID` with the build command's returned `id`. The smoke test runs
on a copied workspace with no network, model access or host credentials. This
checks packaging and launch behavior, not research quality. See the
[complete smoke task and launch contract](executable-harness.md#package-and-smoke-test-a-harness)
for null model fields, absent problem-service fields, workspace permissions and `PATH`.

## Full local agent run with Dungeness

Install Git, Docker (running), and uv. The current CLI automatically downloads
its tested Dungeness revision on first use and reuses it for later runs.
No manual runtime checkout is needed. For developer overrides and cache details,
see [deployment compatibility](deployment-compatibility.md#local-runtime-compatibility).

From your workspace with the installed current CLI, discover the current problem release and prepare:

```sh
openrsi-space problem current
openrsi-space local run .openrsi/my-agent \
  --problem-release TAG --provider PROVIDER --model MODEL_ID \
  --budget LOCAL_CAP --max-seconds LOCAL_SECONDS --prepare-only
```

Replace the uppercase placeholders. Use the release returned by
`problem current`; update OpenRSI if that release is not installed. An optional
`--dungeness PATH` override must point to a clean checkout. These commands build
and prepare without reading model credentials or executing the research loop.

For a real integration test, agree on a provider/model, time limit and total local
budget across all attempts. Remove `--prepare-only` and add the matching credential
option. For an API-key provider, use `--provider-token-env MODEL_API_KEY` with a
securely supplied environment variable. For other supported methods or ensembles,
see [model access](live-models.md). Keep credentials outside the source package.
A local login file alone is not permission for an agent to consume model allowance.

A model-enabled local run **uses your model account**. Track cumulative usage across
retries; it is separate from remote-run authorization. In-flight responses can
exceed the normalized-credit cap. No Yukon login or private verifier repository
is required, and local execution does not submit to OpenRSI's hosted API.
The separate `problem current` discovery command reads the official API.

OpenRSI builds your harness, snapshots the current public problem package, prepares
an independent copy of the selected Dungeness revision, and starts the agent, model gateway,
problem service and evaluator. **You do not need to start a server or expose a port.**
The problem service is a local container on an internal Docker network. The launcher
loads its statement into `OPENRSI_TASK` before your agent starts.

New ECDSA runs start with only the blank point-addition stub and trusted neutral
SDK. There is no passing starting candidate. The problem package selects this
initialization for both local and remote runs; harness source cannot override it.

Add `--prepare-only` to build and inspect the generated configuration without reading
model credentials or starting the agent. Remove that flag to run; unchanged harness
builds are reused. If your package already has `evaluation.json`, provider/model,
budget and token/time settings can come from it instead of command-line overrides.

For example, after authorizing API-key model use:

```sh
openrsi-space local run .openrsi/my-agent \
  --provider openai --model gpt-5.6-sol \
  --budget 1 --provider-token-env OPENAI_API_KEY
```

For ensembles, use `evaluation.json` with its models list and
`--provider-access-file /private/path/providers.json` as described in
[model access](live-models.md). Keep all credential files outside harness source.
Temporary access is placed outside the retained run and removed on completion or
interruption. ChatGPT refresh credentials stay in your original local login.

Prices default to OpenRSI's pinned schedule. `--pricing PATH` accepts a trusted
local pricing JSON with `entries` for additional models; the selected schedule is
saved in the generated runtime. Local pricing does not change official rates.

The command streams Dungeness output and finishes with a JSON summary containing
status, usage, metrics, and artifact paths. Results live under
`.openrsi/local/LOCAL_RUN_ID/`: `run.json` is the summary, `problem.zip` and
`harness.zip` contain the input snapshots, and the Dungeness run directory recorded in `run.json`
contains Dungeness's records, usage events, traces and candidate artifacts. Ctrl-C
asks Dungeness to stop its containers before temporary access is removed.

The ECDSA evaluator retains the exact source of each distinct passing candidate
under the run's `usage/passing-candidates/` directory. A later invalid candidate
or agent error does not overwrite these snapshots. On updated remote workers,
the best retained, trusted evaluation can become the official result even when
research ends with an error, provided screening and accounting checks pass.
Local evaluation results alone are not official remote scores.

The public CLI and remote service share task and harness assembly, so neither needs
a second handwritten copy of OpenRSI's problem configuration. The remote service
additionally performs admission, source screening, isolated verification and receipt
issuance. Local runs do not apply private anti-cheat policy or issue official receipts.
Use the service's pinned runtime and prices when comparing development results.
Linux is the supported platform for comparison with production verification; macOS
Docker runs remain development evidence. Allow memory for both the 8 GiB verifier
and the agent, in addition to Docker overhead.

## Move to the official evaluation

### Platform-funded remote runs

When funding is enabled, the CLI must upload a private evidence bundle from an
ended matching local run. Keep its `run.json`, Dungeness records and usage
logs together; pass `--platform-funded --local-run PATH`. Existing qualifying
runs can be reused. The CLI does not spend automatically.

The recorded local budget cap must be **at least the requested remote cap**.
A $2 local cap with $1.73 spent qualifies for a $2 remote request; a $1 local cap
does not. There is no minimum-spend percentage. The exported bundle is separate from public
harness source and is limited to **192 MiB and 1,000 model calls**. It includes
recorded model exchanges, accounting and evaluation events for private screening
and sampled LLM review. Source, problem, model (or supported provider equivalent) and reasoning settings
must match; the official remote run starts fresh, without your local candidates
or notes. A valid local circuit is not required.

Local testing still uses your authorized model account. Check
`openrsi-space remote funding-policy` **before** choosing the local provider/model.
Every new funded submission requires local evidence; there is no exemption. See
[the funded guide](platform-funded-inference.md) for allowances and admission.

### User-funded remote runs

`openrsi-space remote submit` automatically reuses matching records under the selected
`--state` directory's `local/`, or the harness's `.openrsi/local/`. No duplicate
test, automatic local spending, or trace upload occurs. The record must show a
completed command-harness run, no runtime trial errors, settled accounting, and
a successful accounted response from every declared model. A valid circuit or
minimum spending amount is not required. Budget-triggered shutdown can qualify.

Harness source, model (or supported provider equivalent), reasoning settings and assigned problem must match.
The recorded local budget cap must cover the remote budget. Actual spending,
token and time limits may differ from the remote limits. Runtime
revisions need not be identical; the recorded command interface must be compatible.
This is a CLI readiness check, not trusted evidence or an anti-cheat guarantee.
Existing older records are recognized by their exact local problem-package hash.

If the records are elsewhere, supply the local run directory, its `run.json`, or
Dungeness's `record.json` with adjacent `usage/events.jsonl`:

```sh
openrsi-space remote submit ./my-harness --local-run /path/to/local-run
```

A directly launched Dungeness run must retain the OpenRSI harness-source and
problem identities and the `local-development` label to match. Keep the run's
artifact folder intact. If local testing is blocked or intentionally omitted,
stop and report the blocker. A new hosted submission requires an ended matching
local run and its bundle; the requirement cannot be skipped.
Unchanged saved submission retries remain usable without rerunning local tests.
Status, wait, cancellation and receipt publication never require this check.

Before proceeding, inspect startup, model/tool calls, workspace edits, candidate
evaluation responses, metered usage and shutdown. Test interrupted attempts and
recovery with synthetic fixtures too. Fix failures in the general-purpose harness
and rerun from fresh state; never copy generated solutions or task-specific notes
into later runs. Report the release/digest, runtime revision, checks completed or
skipped, local results and total usage. A successful build is not a passing research
loop, and a failed candidate is different from a harness crash.

When ready, follow the [solver guide](solver-guide.md) to submit the source and
temporary model access to the remote service. After receiving the receipt,
`yukon run` retrieves and validates that retained result without starting another run.

Operator tests involving the API, Dungeness, gateway or a mock model provider live
in `openrsi-space-verifier`. Solvers do not need that private checkout.

## Local outcomes and diagnostics

A completed Harbor command is not necessarily a successful harness trial. The
client checks the retained trial outcome, returns nonzero for failure, and
prints structured diagnostics and the agent exit code when available. A run with
no accounted model requests is explicitly ineligible as local evidence; it may
still be a successful model-free mechanics test. No valid circuit is required
for readiness evidence.

The final JSON separates these outcomes:

- `runtime_exit_code` and `runtime_record_status`: runtime completion, before
  the client checks nested trial failures.
- `agent_exit_code`: the harness process exit code, when retained. Recognized
  structured client results also appear in `agent_reported_outcome`, including
  the last session's stop reason and HTTP status. These are agent-reported
  diagnostics; a recovered session error is not automatically a failed run.
- `candidate_evaluations`: whether the local evaluator observed a valid candidate,
  its best score and evaluation count when recorded. This does not establish
  that the final saved candidate is valid. `metrics` includes available evaluator
  summary metrics, never scores inferred from harness stdout.
- `local_evidence_precheck_passed`: ended execution with complete, settled model
  exchanges, including an ended failed or cancelled run. This is a preliminary
  check, not hosted acceptance; it does not change the execution outcome.
  Source, problem, model/reasoning, complete exchanges and the recorded local
  budget cap must still match. Actual spending need not reach that cap.

During execution the CLI prints model-request and spending progress every 15
seconds from `usage/summary.json`. Harbor's captured stdout may arrive only at
trial completion; use the live usage file for progress. The final summary points
to local exception/output files without echoing arbitrary log bodies or secrets.
`run-status` reads the agent deadline set at launch; remaining research time
excludes image building and service startup.

`problem_identity.release_manifest_sha256` matches `problem current`'s version.
`problem_identity.assembled_package_sha256` identifies the generated task package
(the older `problem.version` field). They name different objects and need not
be equal. Do not edit either hash in retained evidence.

### Retained-run outcome diagnostics

Local diagnostics report wrapper execution and nested model-client outcomes
separately. A wrapper can exit successfully after Codex reports a failed turn or
nonzero exit. `final_verification` reads the retained trusted verifier's
`score.json`; it is separate from intermediate candidate evaluations, and an
invalid penalty score is never a valid result. Missing verifier files are reported
as `not_retained`, not success. No inference is needed to inspect these files.

`local_evidence_precheck` checks retained model exchanges and settled accounting.
It is not an admission guarantee: matching source/problem/model/reasoning,
a sufficient recorded cap, and the hosted review still apply. A nested client
failure does not by itself invalidate otherwise usable local evidence.
