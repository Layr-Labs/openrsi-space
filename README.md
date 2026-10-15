# Catalyst

Catalyst evaluates autonomous research harnesses on **ecdsa.fail**. Solvers
submit harness source; Catalyst builds and runs it under controlled conditions,
meters model use, and independently verifies candidate circuits.

Compare harnesses at **$10, $20, $50 and $100 in model credits, plus Best achieved**. At each tier,
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

Each evaluation runs under the solver's chosen spending cap. **Within $10**, **Within $20**, **Within $50**,
**Within $100**, and **Best overall** are display views over the saved curve;
a $5 run qualifies for all four budget views. Changing the view never starts a run.
Catalyst exports the existing Dungeness evaluator history and settled usage.

See [budget accounting](docs/tier-accounting.md) for exact eligibility and
[the challenge UI](docs/challenge-ui.md) for the local preview and Yukon handoff.

The [ECDSA statement](src/catalyst/problem-set/ecdsa.fail.md) is maintained in
Catalyst. Each new run serves its assigned statement through an internal,
read-only [problem service](docs/problem-service.md). See
[the upstream comparison](docs/ecdsa-upstream.md) for the documentation revision
and the separate execution pin.

## Start here

**Bring your own model access.** Catalyst runs your agent on its remote server
using your supplied model credential, consuming **your API credits or subscription
allowance**. Authorize that remote use, provider, model and spending cap before
submitting. Your Yukon key identifies you; it does not fund model calls.

**Autonomous research only.** Replaying or reproducing existing ECDSA
GitHub/leaderboard answers—including memorized answers embedded in an agent's
instructions or knowledge files—is prohibited and rejected when detected.
Papers, ordinary dependencies and the pinned baseline remain allowed.
See [the screening policy](docs/cheat-filter.md).

- **For humans:** [Solver guide](docs/solver-guide.md) — setup, credentials,
  source packaging, a remote run, receipt retrieval and Yukon publication.
- **For coding agents:** [Agent instructions](docs/agent-prompt.md) — the same
  workflow with the runtime contract, budget boundaries and reporting requirements.
- **For your own framework:** [Generic harnesses](docs/generic-harnesses.md) —
  submit an ordinary repository, Dockerfile and entrypoint with its knowledge base.

The current MVP uses **Yukon dev**, benchmark `layr-labs/catalyst`, and the
HTTPS verifier at `https://3.21.93.126`. Use a dev Yukon login; production
Yukon keys do not authenticate to this deployment. No separate Catalyst
password is needed. The current VM enables ChatGPT and Kimi Code access;
see the solver guide for tested paths and remaining compatibility checks.

## Submission workflow

1. Build your harness and choose a provider, exact model and finite spending cap.
2. `uv run catalyst remote submit HARNESS_DIR --wait` uploads source and starts
   the remote run, using its configured model/budget and your separately supplied
   temporary model access. See the guide for the required credential flag and
   per-run overrides. **This step consumes model allowance.**
3. Catalyst prints the evaluation ID, result and `verification.json` path.
   Resume interrupted retrieval with `uv run catalyst remote wait EVALUATION_ID`.
4. Copy the complete receipt into `submission/verification.json`, then run
   `yukon run` to check the retained result.
5. Write a public methodology note and use `uv run catalyst yukon-submit`
   with exact model/harness attribution and dependency declarations. The helper
   calls stock Yukon and registers its execution/receipt binding.

Yukon uploads only the receipt, creates a candidate commit and dispatches the
challenge-owned GitHub Actions workflow. The workflow authenticates with OIDC,
checks the stored problem, source and owner bindings, and retrieves the verified
score and curve. It does not purchase another run. **Pareto submissions are
recorded without merging solution code.** No Yukon backend patch is required.

Harness source and recorded traces stay private by default. Owners can download
retained evidence or publish source and sanitized traces separately; see
[artifact downloads and sharing](docs/artifact-sharing.md). Scores and curves
come from Yukon's official result packet. The challenge UI is implemented in
an isolated Yukon branch and awaits hosting; see [preview and handoff](docs/challenge-ui.md).

## Repository boundary

This repository is the public solver and challenge interface. It contains:

- The `catalyst` CLI, harness source packaging, local Docker smoke tests and examples.
- Pinned problem downloads and local verifier commands.
- Model-credit accounting rules, result validation and the public HTTP/receipt contract.
- `benchmark.json`, the receipt-only GitHub Actions workflow and solver documentation.
- The optional local catalog and synthetic comparison viewer.

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

## Local development

```sh
uv sync --frozen
uv run catalyst problem list
uv run catalyst harness create my-agent --executable --output .catalyst/my-agent
uv run catalyst --help
```

Use [local checks](docs/local-evaluation.md) before submitting. Local checks
are not official evaluations and do not meter model credits.

For the synthetic local catalog (no model calls):

```sh
uv run catalyst demo
uv run catalyst serve
```

Open http://127.0.0.1:8765. The catalog displays contributor-reported or synthetic
records, separately from official remote results.

## Validation

```sh
uv run python -m unittest discover -s tests -v
node --check src/catalyst/static/app.js
```

Service and cross-repository integration tests live in `catalyst-verifier`.
Before making this repository public, follow the [publication checklist](docs/publication.md):
old Git history still contains private implementation even after files are moved.
