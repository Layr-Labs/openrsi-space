# Local checks before a remote run

You do not need Dungeness or the private verification service to prepare a harness.
Choose the depth of testing you need: verify a circuit, smoke-test a package,
or run the full autonomous agent locally with Dungeness.

## Check a candidate circuit

```sh
uv run catalyst problem clone ecdsa.fail .catalyst/ecdsa-workspace
uv run catalyst problem setup ecdsa.fail --workspace .catalyst/ecdsa-workspace
uv run catalyst problem check ecdsa.fail --workspace .catalyst/ecdsa-workspace
```

The clone is pinned. Edit only the allowed candidate paths. These commands use
the upstream verifier on your machine; setup can download dependencies. They do
not run a research agent, isolate all networking or meter model usage, and their
scores are not official remote evidence.

## Check harness packaging and its entrypoint

```sh
uv run catalyst harness create my-agent --executable --output .catalyst/my-agent
uv run catalyst harness build .catalyst/my-agent
uv run catalyst harness smoke BUILD_ID --workspace .catalyst/ecdsa-workspace --problem ecdsa.fail
```

Replace `BUILD_ID` with the build command's returned `id`. The smoke test runs
on a copied workspace with no network, model access or host credentials. This
checks packaging and launch behavior, not research quality.

## Full local agent run with Dungeness

Install Git, Docker (running), and uv. Clone a clean copy of the public runtime:

```sh
git clone https://github.com/Layr-Labs/dungeness.git ../dungeness
```

From your Catalyst checkout, run your executable harness with one command:

```sh
uv run catalyst local run .catalyst/my-agent \
  --dungeness ../dungeness \
  --provider openai-chatgpt --model gpt-6-astra --reasoning-effort high \
  --budget 1 --max-seconds 900 --codex-auth-file
```

This **uses your model account locally** and consumes your subscription allowance.
Choose your own cap and authorize model use before running it. In-flight responses
can exceed the normalized-credit cap. No Yukon login or private verifier repository
is required, and the command does not contact Catalyst's hosted API.

Catalyst builds your harness, snapshots the current public problem package, prepares
a private copy of the chosen Dungeness revision, and starts the agent, model gateway,
problem service and evaluator. **You do not need to start a server or expose a port.**
The problem service is a local container on an internal Docker network. The launcher
loads its statement into `CATALYST_TASK` before your agent starts.

Add `--prepare-only` to build and inspect the generated configuration without reading
model credentials or starting the agent. Remove that flag to run; unchanged harness
builds are reused. If your package already has `evaluation.json`, provider/model,
budget and token/time settings can come from it instead of command-line overrides.

For an API-key model, use an existing environment variable instead of the Codex flag:

```sh
uv run catalyst local run .catalyst/my-agent \
  --dungeness ../dungeness --provider openai --model gpt-5.6-sol \
  --budget 1 --provider-token-env OPENAI_API_KEY
```

For ensembles, use `evaluation.json` with its models list and
`--provider-access-file /private/path/providers.json` as described in
[model access](live-models.md). Keep all credential files outside harness source.
Temporary access is placed outside the retained run and removed on completion or
interruption. ChatGPT refresh credentials stay in your original local login.

Prices default to Catalyst's pinned schedule. `--pricing PATH` accepts a trusted
local pricing JSON with `entries` for additional models; the selected schedule is
saved in the generated runtime. Local pricing does not change official rates.

The command streams Dungeness output and finishes with a JSON summary containing
status, usage, metrics, and artifact paths. Results live under
`.catalyst/local/LOCAL_RUN_ID/`: `run.json` is the summary, `problem.zip` and
`harness.zip` contain the input snapshots, and `dungeness/runs/projects/catalyst/`
contains Dungeness's records, usage events, traces and candidate artifacts. Ctrl-C
asks Dungeness to stop its containers before temporary access is removed.

The public CLI and remote service share task and harness assembly, so neither needs
a second handwritten copy of Catalyst's problem configuration. The remote service
additionally performs admission, source screening, isolated verification and receipt
issuance. Local runs do not apply private anti-cheat policy or issue official receipts.
Use the service's pinned runtime and prices when comparing development results.
Linux is the supported platform for comparison with production verification; macOS
Docker runs remain development evidence. Allow memory for both the 8 GiB verifier
and the agent, in addition to Docker overhead.

## Move to the official evaluation

When ready, follow the [solver guide](solver-guide.md) to submit the source and
temporary model access to the remote service. After receiving the receipt,
`yukon run` retrieves and validates that retained result without starting another run.

Operator tests involving the API, Dungeness, gateway or a mock model provider live
in `catalyst-verifier`. Solvers do not need that private checkout.
