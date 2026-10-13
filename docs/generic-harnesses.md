# Generic harness execution

This implementation separates harness execution from model access in
Dungeness. Harbor still provides the container/job lifecycle. No Yukon change
is required: the remote service continues issuing verification receipts.
The general runtime is deployed on the existing VM in release
`20261013-generic-runtime-1`. The real Docker integration passed with a synthetic
provider, including internet isolation, declared-model enforcement, token
accounting, independent verification and receipt retrieval through stock Yukon.
A live EvoX/Kimi run also completed independent verification, followed by
acceptance through Yukon's hosted GitHub Actions workflow. Its bounded
research run retained the baseline score; measured results are recorded below.

## Submit your own agent

Submit an existing repository containing the harness, knowledge base, prompts,
configuration, helper programs and dependencies, with its existing directory
layout. The harness can run its own workers, search loop or framework.
Provide a Dockerfile and launch command; no Catalyst-specific manifest or
`instructions.md` is required. For example, with `kimi-code` enabled:

```sh
uv run catalyst remote submit /path/to/your-agent \
  --entrypoint "python3 /app/main.py" \
  --provider kimi-code --model k3 --budget 3 \
  --prompt-model-token --wait
```

The command must match the location established by your Dockerfile. Use
`--dockerfile relative/path/Dockerfile` when it is not at the repository root.
`--entrypoint` is parsed as an argument list, not evaluated by a host shell.
If the program needs shell syntax, declare a shell explicitly; it runs only
inside the worker container. The CLI includes generated execution metadata in
the immutable source archive without writing files into your repository.
An existing `harness.json` can declare the same launch information instead;
do not combine it with `--entrypoint`.

An optional editable starter is also available:

```sh
uv run catalyst harness create my-agent --executable
```

Replace `harnesses/my-agent/agent.py`, put reference material in `knowledge/`,
and install dependencies in its Dockerfile. The starter copies the whole source
bundle into `/opt/harness/`, including those reference files. It initially makes
no model calls; implement the research loop before requesting a model run.
An existing framework can use its own entrypoint instead.

Submit the same source with a model choice and spending cap:

```sh
uv run catalyst remote submit harnesses/my-agent \
  --provider kimi-code --model k3 --reasoning-effort high --budget 3 \
  --prompt-model-token --wait
```

The hidden prompt takes a **Kimi Code membership API key**, available from the
[Kimi Code console](https://www.kimi.com/code/console).
Kimi documents subscription-backed API access for third-party coding tools and
the `k3` model in its [official guide](https://www.kimi.com/code/docs/en/).
A Moonshot platform key belongs to the separate `moonshot` provider.
No persistent server-side model account is created; the credential is handed
off for this evaluation and removed afterwards.

`--provider`, `--model` and `--budget` are provider-neutral flags. For example,
select `--provider openai --model gpt-6-astra` with an OpenAI API key, or
`--provider openai-chatgpt --model gpt-6-astra --codex-auth-file` with the existing
ChatGPT handoff instead of the hidden prompt.
The harness's model client must implement the chosen provider's supported
protocol and use the gateway endpoint supplied in `CATALYST_TASK`.
The provider's protocol must be available and enabled by the operator.
New model names do not need a code change or a model whitelist: the service
resolves and freezes reference pricing before accepting the run.
All inference uses the metered gateway.

An `evaluation.json` is optional when all three model/budget flags are provided.
Without a file, the defaults are temporary model access, 100,000 model tokens
and 900 seconds. Override those limits with `--max-tokens` and `--max-seconds`.
With an existing file, flags override its run settings without editing it.
Set provider and model together; switching them clears any inherited reasoning
effort unless `--reasoning-effort` is also given. For ensembles, keep the full
v4 model list in `evaluation.json`; budget and limit flags still apply.

The client saves the resolved run settings for `remote wait` and receipt export,
including across process restarts. Source and knowledge edits change the source
digest; model/budget changes change the evaluation configuration digest.
Both identities are bound into the verification receipt. Yukon still receives
only that receipt and retrieves the existing verified result.

The source archive is limited to 8 MiB and cannot contain symlinks. Install
larger dependencies at image build time and pin their versions. Include the
knowledge files needed at runtime in the image. Keep all credential files
outside the source directory; `.env*`, `.git`, local state and virtual
environments are excluded. A selected credential file inside the source
directory is rejected before submission.

## Source and patch

Changes live in `/Users/bxue/Documents/dungeness-main` on `for-catalyst`, based on
`506890937d75b659db714d3e02ea3d3cec3a1451`. Both repositories are writable in
this session. The runtime is deployed from a hashed source snapshot; the local
changes have not been committed or pushed.

The complete, reviewable upstream patch (including tests) is
[`src/catalyst/runtime/dungeness-command.patch`](../src/catalyst/runtime/dungeness-command.patch).
Catalyst applies it to its isolated per-evaluation checkout before recording
the generated runtime commit. It does not modify the configured source checkout.
The patch is included in the Python package. Once the interface is present in
the pinned upstream checkout, Catalyst uses that implementation.
An incremental `dungeness-provider-contract.patch` upgrades earlier command
interface checkouts with generic Kimi/Moonshot Chat Completions support and
priced-request checks. Additional compatibility patches upgrade older command
runtimes' CLI and Harbor result handling, settle explicit input-validation
rejections without guessing usage for ambiguous errors, and make root-produced
verifier results readable by the host worker. All patches are packaged and
applied only where the corresponding capability is absent.

For another clean checkout at the original pin, apply the patch from an
unrestricted terminal. Do not reapply it to the already patched branch:

```sh
git -C /Users/bxue/Documents/dungeness-main apply /Users/bxue/Documents/catalyst/src/catalyst/runtime/dungeness-command.patch
```

Keep Catalyst configured against a clean committed Dungeness pin until those
upstream changes are deliberately committed; dirty upstream checkouts remain
rejected for reproducibility.

## Execution contract

A Dungeness command agent uses an ordinary Dockerfile and:

```yaml
execution_mode: installed
execution:
  interface: dungeness-command-v1
  entrypoint: ["python3", "/opt/harness/agent.py"]
```

The image needs Python 3 for the trusted launcher; the harness itself can use
any installed language. Command descriptors cannot select `harbor.import_path`.
The compiler selects the trusted `command_agent:CommandAgent` adapter.

Models belong to the run's `model_access.models` list, independently of the
agent. Each profile identifies the provider, request model, API protocol and
pinned pricing identity. The compiler gives the harness a `DUNGENESS_TASK`
JSON file containing the problem instruction, writable workspace, model
endpoints and execution configuration. Real credentials are not in this file.
The compiler does not enable research-state prompt interventions implicitly.

One Harbor trial may run many harness subprocesses. They share the run's
compute envelope, gateway and budget. The launcher forwards termination and
kills remaining process-group children on exit. Container teardown remains
the boundary for processes that deliberately detach themselves.
An optional `execution.resume_entrypoint` supports explicit exit-code-75
continuations under `runtime.continuation` limits. It reuses the same sandbox;
this is not durable recovery after host failure.

Catalyst's existing `catalyst-exec-v1` source interface remains available.
Its wrapper now uses the Dungeness command adapter. `CATALYST_TASK` also
contains `models`, and `CATALYST_MODELS` exposes that list as JSON.
The old Codex identity and Dockerfile marker workaround are removed.

## Models and credentials

Existing `evaluation.json` v3 files select one model. Version 4 additionally
requires `models`, with the default `model` first:

```json
{
  "schema_version": 4,
  "llm_access": {"grant_id": "grant_temporary_provider"},
  "model": {"provider": "openai", "name": "gpt-5.6-sol"},
  "models": [
    {"provider": "openai", "name": "gpt-5.6-sol"},
    {"provider": "openai", "name": "gpt-6-astra"}
  ],
  "max_model_credits": 3,
  "limits": {"max_model_tokens": 100000, "max_seconds": 900}
}
```

The service must establish pricing for every model. The operator must allow **every** selected provider.
Existing service policy is not expanded automatically.
Every nonzero token bucket must also be priced: configurations that report
cache-write tokens for a model without a pinned cache-write rate fail closed.
Such clients must disable cache writes or wait for a versioned pricing update.

## Reference prices for declared models

Existing entries retain the immutable comparison rates in `pricing.json`.
For a model absent from those entries, the client first calls the authenticated
`POST /pricing/quote` endpoint with its declared models, without sending model
credentials. The service fetches the fixed
[OpenRouter models catalog](https://openrouter.ai/docs/api/api-reference/models/get-models).
New OpenRouter model IDs resolve directly; direct OpenAI, ChatGPT and Anthropic
names resolve under their corresponding catalog author, and Moonshot names
under `moonshotai`. Ambiguous or unmatched identities fail before inference.
Subscriptions with opaque aliases need a verifiable identity mapping; callers
cannot assign an arbitrary cheaper reference model.

The server stores each quote by content hash. It includes selected rates,
catalog provenance and hash, the issue/expiry times and the normalization policy.
New quotes expire after one hour; accepted jobs retain their original snapshot.
The client retains the quote and operation key through uncertain responses.
It obtains a fresh quote automatically only after the service explicitly
confirms that an expired operation was never accepted. Existing receipts remain
verifiable after expiry or catalog changes.

Catalog prices are converted from dollars per token to reference credits per
million tokens. Missing cache rates use the input rate, as an explicit
normalization rule. Catalog entries use flat reference rates; these are not
claims about actual subscription charges or provider-specific context tiers.
This first catalog adapter supports text token accounting. Nonzero non-token
prices, paid provider tools, multimodal requests and model fallbacks require
additional accounting and are rejected. Agent-executed function tools remain
available. The service never accepts solver-authored prices or upstream URLs.

The worker installs the frozen snapshot in its trusted Dungeness runtime.
The gateway uses it for admission/accounting; Catalyst uses the same snapshot
to verify the complete usage ledger, intermediate scores and final receipt.
Raw counts remain available for later comparison under another reference schedule.
No Yukon backend change is needed.

The catalog fetch uses a five-minute in-process cache and has bounded response
size and timeout. Catalog failure never falls back to invented prices.
If the catalog endpoint requires authentication, the operator can supply
`CATALYST_OPENROUTER_CATALOG_TOKEN` in the service environment. This credential
is used only at that fixed catalog URL, never taken from solver model access,
and is excluded from snapshots and worker environments. Redirects are refused.

For a single API provider, use the existing hidden token prompt or stdin
handoff. This includes subscription-backed Kimi Code API keys, using the
`kimi-code` provider and `k3` model; normalized credits do not claim an actual
cash charge. Multiple providers can use `--provider-access-file` pointing to a
private JSON map of provider names to access tokens. For `openai-chatgpt`,
the map value is the temporary access object produced from the local Codex
login; it must not contain a refresh token. For ChatGPT alone, keep using
`--codex-auth-file`. Neither credential file belongs in the harness directory.

The same authenticated HTTPS/private worker channel carries the credentials.
The worker stages them in Linux tmpfs. API keys reach only the gateway's
environment; ChatGPT access is mounted only into the gateway. The harness uses
the public `testbed` placeholder. Credentials are removed after the run and
excluded from receipts and published evidence.

ChatGPT is a Responses provider, not a universal substitute for every
framework's model client. The Codex examples support the new gateway mode
without reading native authentication from the harness container. Live
compatibility of that change still needs an explicitly authorized paid smoke run.
Kimi Code and Moonshot support ordinary Chat Completions clients as well as
the existing Responses adapter. For streamed chat requests, the gateway
requests the final usage chunk and drains it even if the agent disconnects.

## Parallel accounting and evaluation

The gateway authorizes provider/model pairs before contacting the provider.
All admitted requests share one ledger and a bounded number of active slots.
Credits are reserved until the upstream response has drained and settled;
client disconnection does not release the reservation prematurely.
Missing usage blocks further admissions. Explicit HTTP 400 input-validation
errors with an `invalid_request_error` body settle at zero tokens, with the
rejection basis retained in the ledger. Successful responses without usage,
interrupted streams, and ambiguous errors still block further inference.
Catalyst prices each settled receipt using that receipt's authorized model,
then checks the terminal total.

Reservations limit concurrent admission; they are **not a hard provider billing
cap**. Actual usage can exceed an allowance, especially with subscription
protocols that lack enforceable per-call cost limits. The gateway then blocks
new calls, and Catalyst rejects totals exceeding the run's cap. No cost is
clipped to make a result eligible. Use provider-side spending limits where
available. Strict pre-call cost guarantees remain future work.

`evaluate --json PATH` submits a file or directory snapshot and prints the
trusted evaluator's structured response. For the pinned ECDSA directory
interface this includes score, validity, candidate/source digests, evaluation
ID and run ID. Concurrent harness workers may submit different candidate
directories; the trusted ECDSA sidecar serializes verification to protect its
build workspace. Parallel verifier capacity is not implemented.

The existing history exporter accounts conservatively for calls in flight
when an evaluator observation arrives. The full cost/performance curve and
$20/$200/Best views are preserved.

## Example and verification

[`harnesses/ecdsa-ensemble`](../harnesses/ecdsa-ensemble) is a small Python
example using two worker processes and two model configurations, with no
Codex dependency. Workers propose complete Rust modules, evaluate independent
snapshots, and promote the best verified candidate. This is an interface
example, not an implementation of EvoX or OpenEvolve.

After deploying this version and enabling the `openai` provider, a solver can
submit it using:

```sh
.venv/bin/catalyst remote submit harnesses/ecdsa-ensemble --prompt-model-token --wait
```

That command would launch a paid evaluation; it was not run during development.

Offline checks cover generic compiler output, arbitrary source and knowledge
packaging, per-run CLI settings and resumable receipt bindings, process workers and cleanup,
concurrent gateway calls against a mock provider, shared credit reservations,
provider allowlists, mixed-model pricing and delayed-stream checkpoint costs.
The full Mac suite passed 205 tests with three optional skips. The deployed
server suite passed 200 tests with eight optional skips. Additional checks
passed all 66 gateway tests, eight runtime/permission tests, and six EvoX
adapter tests, including the actual framework using synthetic responses.

## Framework integration and runtime check

[`harnesses/ecdsa-evox`](../harnesses/ecdsa-evox) packages actual SkyDiscover/EvoX
at a fixed upstream commit. Its ECDSA evaluator adapter keeps the best verified
Rust directory. Main, guide and search-strategy models share the declared
gateway endpoints, with no runtime internet or default public-provider fallback.
The default test configuration is Kimi Code `k3` and $3 normalized credits.
This is a short integration run, not a research-performance comparison.

The following runs actual Docker, Dungeness, a local API and the Yukon CLI
with synthetic model responses. It incurs no model charges:

```sh
.venv/bin/python scripts/check-local-e2e.py \
  --dungeness /path/to/clean-pinned-dungeness \
  --yukon /path/to/yukon \
  --harness tests/fixtures/generic-runtime
```

The fixture checks absent public routing and provider credentials, rejects an
undeclared model, calls the model gateway, and leaves a
background child for the command adapter to terminate. The outer test checks
the verified score, receipt replay, durable result, private artifacts and API
worker shutdown. The tiny fixture is independently verified after execution;
the real ECDSA task additionally supplies the in-run evaluator. This requires
Docker socket access and local TCP listeners.

The Docker integration completed on October 9 with one model request, verified
scores `[3, 0.25]`, exactly one evaluation, and repeated receipt retrieval.
Its generated test runner binds the synthetic circuit identity; the production
command remains pinned to ECDSA.

The live ECDSA attempts are retained for audit:

- `19eaf05f-3251-458f-a109-7d10aaaf4a4f`: two Kimi requests rejected before
  generation because EvoX sent an empty system message. The old gateway failed
  closed on missing usage; the Harbor verifier also hit a result-permission error.
- `24325238-effb-48b2-8f5c-859f1fc4ef38`: verifier permissions and rejection
  accounting passed. Kimi rejected five requests because EvoX selected an
  unsupported temperature. All five settled at zero tokens.
- `0b48d992-00e9-4567-ad47-459767195757`: corrected K3 completion parameters and
  an early metered configuration probe; submitted with the original $3 cap.
  Completed independent verification with four trusted observations and ten
  settled model calls totaling 0.685212 normalized credits (84,105 budget
  tokens). Harbor stopped the agent at the configured 900-second limit.
  All observations matched the baseline product, 10,758,874,395; there was
  no verified performance improvement. The Pareto pair is
  `[10758874395, 0.000276]`, using cost at the earliest best observation,
  rather than total run cost. Stock `yukon run` retrieved this exact result
  without starting another evaluation.
  Yukon dev accepted submission `22f76880-5436-497d-a403-beab576a4f14`
  on October 13, 2026. Its hosted GitHub Actions workflow retrieved the same
  score pair and four-observation curve from the remote service. The evaluated
  receipt commit is `3d63930bda5499eca6ceef2571a0e97aaafed0e0`, against
  benchmark source `5c9b3c08ab4bd3c1cdf61bb6e73cb3e2943a022d`.
