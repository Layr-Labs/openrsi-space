# Catalyst

**Versioned-release rollout:** this branch includes new `v0`/`v1` problem
manifests. The hosted evaluator at `https://3.21.93.126` remains pinned to the
earlier manifest until the coordinated service and Yukon registration update.
For submissions to that deployment, use commit `41e5767` in a separate checkout.
The new manifests are not interchangeable with historical problem hashes.

Catalyst is a benchmark for research agent harnesses on **ecdsa.fail**. Submit
your own harness, using your own model account, to run in a controlled environment
on Catalyst's servers. Its performance is independently verified and can be
compared with others on a public leaderboard.

New research runs start from a **blank point-addition scaffold** and a neutral
circuit SDK. The scaffold declares the input/output registers but contains no
algorithm or valid baseline score. Submit a general-purpose research harness.
The task service supplies the same pinned library of **50 raw research papers**
to every run. Do not bundle problem-specific material in the submitted harness.

Compare harnesses at **$10, $20, $50 and $100 in model credits, plus Best achieved**. At each tier,
rank the best eligible verified `avg_toffoli × peak_qubits`; lower is better.
Best achieved considers the full verified run without a fixed comparison budget
and displays credits consumed at that candidate. Every run still has an explicit
finite spending cap and execution timeout. New evaluations have no model-token
ceiling by default; token usage is still metered. Use `--no-token-limit` to
clear a ceiling inherited from an older manifest, or `--max-tokens N` to set
one deliberately. There is no $2,000 comparison tier.
Keep the complete performance–cost curve and every attempt, including failures
and regressions. Infrastructure costs are accounted for separately.

Model credits retain existing immutable reference rates in
[`pricing.json`](src/catalyst/pricing/pricing.json).
The service resolves additional declared models through a
[service-issued OpenRouter pricing snapshot](docs/generic-harnesses.md#reference-prices-for-declared-models).
The exact schedule's content hash is bound into every evaluation and
verification reference. These are comparison rates. Subscription usage can consume account
allowance without representing a cash charge. Unknown usage or unpriced models
cannot establish tier eligibility.

Each evaluation runs under the solver's chosen spending cap. **Within $10**, **Within $20**, **Within $50**,
**Within $100**, and **Best overall** are display views over the saved curve;
a $5 run qualifies for all four budget views. Changing the view never starts a run.
Catalyst exports the existing Dungeness evaluator history and settled usage.

See [budget accounting](docs/tier-accounting.md) for exact eligibility.
The challenge UI is maintained in Yukon; see [the UI integration](docs/challenge-ui.md).

The [ECDSA statement](src/catalyst/problem-set/ecdsa.fail.md) is maintained in
Catalyst. Each new run serves its assigned statement through an internal,
read-only [problem service](docs/problem-service.md). See
[the upstream comparison](docs/ecdsa-upstream.md) for the documentation revision
and the separate execution pin.

For Grok, use a [Grok CLI session or direct xAI API key](docs/grok.md);
an OpenRouter account is optional.

Submission controls have no daily count cap by default. Concurrency and short-window
limits still apply; see [limits and retry instructions](docs/solver-guide.md#submission-limits-and-retries).

## Start here

**Your harness. Your model account.** You start each run, choose its spending and
time limits, and can monitor progress or request cancellation through the CLI at
any time while it is active. Model calls use your API credits or subscription
allowance. Your Yukon key identifies you; it does not fund model calls.

Catalyst receives model access for the run you start. Login-file handoffs keep
refresh credentials on your device. Supplied access tokens and API keys are used
only for that run and removed during run cleanup. Authorize the provider, model,
limits and remote credential use before submitting.

You are responsible for ensuring your use complies with your model provider's terms.

**Autonomous research only.** Replaying or reproducing existing ECDSA
GitHub/leaderboard answers—including memorized answers embedded in an agent's
instructions or knowledge files—is prohibited and rejected when detected.
General-purpose frameworks and tools are allowed. ECDSA-specific papers, notes,
strategies and prewritten candidates in submitted source are prohibited; use the
server-assigned task and shared paper library during the run.
See [the screening policy](docs/cheat-filter.md).

- **For humans:** [Solver guide](docs/solver-guide.md) — setup, credentials,
  source packaging, a remote run, receipt retrieval and Yukon publication.
- **For coding agents:** [Agent instructions](docs/agent-prompt.md) — the same
  workflow with the runtime contract, budget boundaries and reporting requirements.
- **For your own framework:** [Generic harnesses](docs/generic-harnesses.md) —
  submit an ordinary agent repository, Dockerfile and entrypoint.
- **Before choosing an agent/model pair:** [Harness compatibility](docs/harness-compatibility.md) —
  match API formats, helper calls and credentials, then check the adapter.

The current MVP uses **Yukon dev**, benchmark `layr-labs/catalyst`, and the
HTTPS verifier at `https://3.21.93.126`. Use a dev Yukon login; production
Yukon keys do not authenticate to this deployment. No separate Catalyst
password is needed. The current VM enables `openai-chatgpt`, `xai`
and `grok-subscription`. Availability does not guarantee that every agent/model
pair is compatible; see the solver guide and harness compatibility checks.

## Submission workflow

Find agents in the [ranked public harness catalog](https://3.21.93.126/public/harnesses).
Use `uv run catalyst harness search --max-credits 8`, then
`uv run catalyst harness download EVALUATION_ID --output harness.zip` to download
selected published source without login. See [search, ranking and downloads](docs/harness-catalog.md).

1. Build your harness and choose a provider, exact model and finite spending cap.
2. `uv run catalyst remote submit HARNESS_DIR --wait` uploads source and starts
   the remote run, using its configured model/budget and your separately supplied
   temporary model access. See the guide for the required credential flag and
   per-run overrides. **This step consumes model allowance.**
3. Catalyst prints the evaluation ID, result and `verification.json` path.
   Resume interrupted retrieval with `uv run catalyst remote wait EVALUATION_ID`.
4. Create `submission/` and copy the complete receipt into `submission/verification.json`, then run
   `yukon run` to check the retained result.
5. Write a public methodology note and use `uv run catalyst yukon-submit`
   with exact model/harness attribution and dependency declarations. The helper
   calls stock Yukon and registers its execution/receipt binding.

Yukon uploads only the receipt, creates a candidate commit and dispatches the
challenge-owned GitHub Actions workflow. The workflow authenticates with OIDC,
checks the stored problem, source and owner bindings, and retrieves the verified
score and curve. It does not purchase another run. **Pareto submissions are
recorded without merging solution code.** No Yukon backend patch is required.

New harness submissions require public source, published after the run stops and
credential screening passes. Traces are retained internally and cannot be downloaded or published. Existing private runs stay private. Owners can
download harness source or add an authorized license; see
[artifact downloads and sharing](docs/artifact-sharing.md). Scores and curves
come from Yukon's official result packet. The challenge UI lives in Yukon; see [the integration guide](docs/challenge-ui.md).

## Repository boundary

This repository is the public solver and challenge interface. It contains:

- The `catalyst` CLI, harness packaging, smoke tests, full local Dungeness runs and a starter generator.
- Pinned problem downloads and local verifier commands.
- Model-credit accounting rules, result validation and the public HTTP/receipt contract.
- `benchmark.json`, the receipt-only GitHub Actions workflow and solver documentation.

The **private `catalyst-verifier` repository** contains the verification API,
queue, Dungeness worker adapter, anti-cheat implementation, credential handling
inside the service, artifact storage and deployment tooling. It depends on the
public `catalyst-research` package; this package does not depend on the service.
Dungeness is not required for remote submission. Its
[public repository](https://github.com/Layr-Labs/dungeness) is available for
optional full local agent tests.
See [local testing options](docs/local-evaluation.md).
The hosted challenge UI remains in Yukon's challenge application.

The service and client communicate over the [public HTTP contract](docs/remote-evaluation.md).
A receipt identifies retained evidence; it contains no model credential and
cannot authorize a score by itself. Verification retrieval never launches a paid run.

The repository does not bundle example agents or a submission source directory.
Generate a starter below, or submit your own repository. Only the generated
`submission/verification.json` receipt is uploaded to Yukon. The root
`verification.json` is the retained baseline; leave it unchanged.

## Local development

```sh
uv sync --frozen
uv run catalyst problem list
uv run catalyst harness create my-agent --executable --output .catalyst/my-agent
uv run catalyst --help
```

For a full local research run with model accounting:

```sh
uv run catalyst local run .catalyst/my-agent --dungeness ../dungeness \
  --provider openai-chatgpt --model gpt-6-astra --reasoning-effort high \
  --budget 1 --codex-auth-file
```

This uses your local model account and starts its internal services automatically.
Add `--prepare-only` to build and inspect without making model calls. See
[local testing](docs/local-evaluation.md) for prerequisites, API keys, ensembles,
artifacts and limits. Local runs cannot issue official Yukon receipts.

## Validation

```sh
uv run python -m unittest discover -s tests -v
```

Service and cross-repository integration tests live in `catalyst-verifier`.
See [publication notes](docs/publication.md) for the public/private source boundary.

### Harness visibility

New remote submissions require public harness source. It is published after the
run stops and credential screening passes. Private submissions are not supported.
Traces are retained internally. No source license is assigned automatically. Review
files and third-party rights before submitting; see [artifact sharing](docs/artifact-sharing.md).
