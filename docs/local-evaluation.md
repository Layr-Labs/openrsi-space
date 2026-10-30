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
bundle with settled local spending of at least the full remote cap; user-funded
runs can explicitly skip the CLI check. See [funded requirements](platform-funded-inference.md).
Neither local scores nor successful tests guarantee a receipt.

## Check a candidate circuit

```sh
uv run openrsi-space problem clone ecdsa.fail .catalyst/ecdsa-workspace
uv run openrsi-space problem setup ecdsa.fail --workspace .catalyst/ecdsa-workspace
uv run openrsi-space problem check ecdsa.fail --workspace .catalyst/ecdsa-workspace
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
uv run openrsi-space harness create my-agent --executable --output .catalyst/my-agent
uv run openrsi-space harness build .catalyst/my-agent
uv run openrsi-space harness smoke BUILD_ID --workspace .catalyst/ecdsa-workspace --problem ecdsa.fail
```

Replace `BUILD_ID` with the build command's returned `id`. The smoke test runs
on a copied workspace with no network, model access or host credentials. This
checks packaging and launch behavior, not research quality. See the
[complete smoke task and launch contract](executable-harness.md#package-and-smoke-test-a-harness)
for null model fields, absent problem-service fields, workspace permissions and `PATH`.

## Full local agent run with Dungeness

Install Git, Docker (running), and uv. Clone a clean copy of the public runtime:

```sh
git clone https://github.com/Layr-Labs/dungeness.git /absolute/path/to/dungeness
```

For a known-compatible pin and instructions for an older runtime, see
[deployment compatibility](deployment-compatibility.md#local-runtime-compatibility).

From your OpenRSI checkout, discover the current problem release and prepare:

```sh
uv run openrsi-space problem current
uv run openrsi-space local run .catalyst/my-agent \
  --dungeness /absolute/path/to/dungeness \
  --problem-release TAG --provider PROVIDER --model MODEL_ID \
  --budget LOCAL_CAP --max-seconds LOCAL_SECONDS --prepare-only
```

Replace the path and uppercase placeholders. Use the release returned by
`problem current`; update OpenRSI if that release is not installed. The runtime
checkout must be clean. These commands build and prepare without reading model
credentials or executing the research loop.

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
a private copy of the chosen Dungeness revision, and starts the agent, model gateway,
problem service and evaluator. **You do not need to start a server or expose a port.**
The problem service is a local container on an internal Docker network. The launcher
loads its statement into `CATALYST_TASK` before your agent starts.

New ECDSA runs start with only the blank point-addition stub and trusted neutral
SDK. There is no passing starting candidate. The problem package selects this
initialization for both local and remote runs; harness source cannot override it.

Add `--prepare-only` to build and inspect the generated configuration without reading
model credentials or starting the agent. Remove that flag to run; unchanged harness
builds are reused. If your package already has `evaluation.json`, provider/model,
budget and token/time settings can come from it instead of command-line overrides.

For example, after authorizing API-key model use:

```sh
uv run openrsi-space local run .catalyst/my-agent \
  --dungeness /absolute/path/to/dungeness --provider openai --model gpt-5.6-sol \
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
`.catalyst/local/LOCAL_RUN_ID/`: `run.json` is the summary, `problem.zip` and
`harness.zip` contain the input snapshots, and `dungeness/runs/projects/catalyst/`
contains Dungeness's records, usage events, traces and candidate artifacts. Ctrl-C
asks Dungeness to stop its containers before temporary access is removed.

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

When funding is enabled, the CLI must upload a private evidence bundle from a
completed matching local run. Keep its `run.json`, Dungeness records and usage
logs together; pass `--platform-funded --local-run PATH`. Existing qualifying
runs can be reused. The CLI does not spend automatically.

Actual settled local usage must be **at least the full requested remote cap**:
20 local credits for a 20-credit remote run. A larger configured cap with less
actual usage does not qualify. The exported bundle is separate from public
harness source and is limited to **192 MiB and 1,000 model calls**. It includes
recorded model exchanges, accounting and evaluation events for private screening
and sampled LLM review. Source, problem, provider/model and reasoning settings
must match; the official remote run starts fresh, without your local candidates
or notes. A valid local circuit is not required.

Local testing still uses your authorized model account. Check
`openrsi-space remote funding-policy` **before** choosing the local provider/model.
Only an operator exemption can bypass funded evidence requirements. See
[the funded guide](platform-funded-inference.md) for allowances and admission.

### User-funded remote runs

`openrsi-space remote submit` automatically reuses matching records under the selected
`--state` directory's `local/`, or the harness's `.catalyst/local/`. No duplicate
test, automatic local spending, or trace upload occurs. The record must show a
completed command-harness run, no runtime trial errors, settled accounting, and
a successful accounted response from every declared model. A valid circuit or
minimum spending amount is not required. Budget-triggered shutdown can qualify.

Harness source, provider/model/reasoning settings and assigned problem must match.
Local spending, token and time limits may differ from the remote limits. Runtime
revisions need not be identical; the recorded command interface must be compatible.
This is a CLI readiness check, not trusted evidence or an anti-cheat guarantee.
Existing older records are recognized by their exact local problem-package hash.

If the records are elsewhere, supply the local run directory, its `run.json`, or
Dungeness's `record.json` with adjacent `usage/events.jsonl`:

```sh
uv run openrsi-space remote submit ./my-harness --local-run /path/to/local-run
```

A directly launched Dungeness run must retain the OpenRSI harness-source and
problem identities and the `local-development` label to match. Keep the run's
artifact folder intact. If local testing is blocked or intentionally omitted,
report the untested steps and add `--skip-local-check` to your submission command.
This flag does not authorize spending or credential transfer by itself. The choice
is recorded in the local remote-session metadata; local traces stay on your machine.
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
in `catalyst-verifier`. Solvers do not need that private checkout.
