# OpenRSI

[Install the current submission CLI](docs/solver-guide.md#install-the-current-submission-cli). Local testing and remote verification need no Yukon benchmark clone.

Local runs automatically fetch and reuse the tested Dungeness revision bundled with
the CLI. Updating the CLI selects its runtime for new runs; it does not modify
existing runs. No manual Dungeness clone is required. See
[managed runtime and developer overrides](docs/deployment-compatibility.md#local-runtime-compatibility).

[![Checks](https://github.com/Layr-Labs/openrsi-space/actions/workflows/check.yml/badge.svg)](https://github.com/Layr-Labs/openrsi-space/actions/workflows/check.yml)

OpenRSI is a benchmark for research agent harnesses. You submit your own
harness to run in a controlled environment on
OpenRSI's servers so that its performance can be independently verified and
compared with others on a public leaderboard.
The initial challenge is **ecdsa.fail**.

This repository contains the solver CLI, challenge resources, accounting contracts
and Yukon receipt integration. Dungeness executes harnesses; the private
`openrsi-space-verifier` service manages official evaluations. Yukon hosts the UI.

The platform is **OpenRSI**; the solver command is **`openrsi-space`**.
The repository is **`Layr-Labs/openrsi-space`**. Existing runs remain readable. Install the CLI from current `main` using the command below.
The command and installed distribution are `openrsi-space`; the Python package
is `openrsi_space`. New local records use `.openrsi/`, and configuration uses
`OPENRSI_*` environment variables.

Accepted remote results appear automatically on the OpenRSI dashboard. Remote
run status is public; only accepted, verified results receive ranked scores.
Yukon publication is optional: it adds an account-linked submission and repository
record without another research run. Stopping the CLI or revoking your Yukon key
does not remove an accepted result from the OpenRSI dashboard. Private local
execution evidence, raw logs and credentials are not part of the public feed.

## Get started

```sh
uv tool install --force --refresh "git+https://github.com/Layr-Labs/openrsi-space.git@main"
export PATH="$(uv tool dir --bin):$PATH"
hash -r
mkdir -p openrsi-workspace
cd openrsi-workspace
openrsi-space problem current
```

Run the installed CLI directly. Use this ordinary folder for harnesses and run
records. A Yukon account is required for remote authentication, but the Yukon CLI
and a pinned benchmark checkout are only needed for optional manual publication.
Follow the [solver guide](docs/solver-guide.md) for authentication and local testing.

Already testing or submitting and something failed? Start with the
[submission recovery guide](docs/submission-recovery.md) before rerunning or
changing your harness. It explains IDs, reconnecting, reusable evidence, and
publication retries.

Local development can use your existing Codex/ChatGPT or Claude subscription, or
a supported model API. Official remote runs use **Eigen Labs-funded OpenRouter**;
you authenticate with a Yukon key and send no personal model credential.
**Codex/ChatGPT and Claude subscription runs qualify for supported equivalent models.**
The recorded local budget cap must cover the requested remote budget; actual local spending may be lower. An ended matching local run is required.
No personal OpenRouter key is required. Check
[eligibility and the separate local/remote budgets](docs/platform-funded-inference.md#local-access-and-remote-eligibility)
before spending. Publishing the verified receipt makes no new model calls.

This repository is currently internal. Sign in to GitHub with organization access;
if the link returns 404, request access. Repository access is not model access.

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```sh
openrsi-space --help
openrsi-space --version
openrsi-space problem list
openrsi-space harness create my-agent --executable --output .openrsi/my-agent
```

The starter makes no model calls. Follow the [solver guide](docs/solver-guide.md)
to build a general-purpose harness, [test it locally with Dungeness](docs/local-evaluation.md),
then submit it for an official evaluation. Docker is needed for local integration tests. New submissions require public
harness source; review files before uploading. You authorize each paid run and
are responsible for complying with your model provider's terms.

`remote submit` reuses a matching ended local run. Use `--local-run PATH`
for records elsewhere. Every new hosted submission requires a matching ended
local run bundle; there is no skip option or evidence exemption. A failed or
cancelled run can qualify when all model exchanges and accounting are complete;
its failure status is retained. See the [evidence rules](docs/platform-funded-inference.md).

### Before submitting

- **Public source:** both the ZIP and expanded harness source must fit **8 MiB**
  by default. Check `openrsi-space remote limits ./my-harness`; exclude
  credentials, generated outputs and problem-specific material.
- **Funded runs, when enabled:** check `openrsi-space remote funding-policy`
  for funded providers and limits. You choose the exact model; its pricing must validate. Use `--platform-funded --local-run PATH`;
  no personal model credential is sent for the remote run.
- **Local evidence:** retain an ended matching Dungeness run and its logs.
  The CLI uploads a separate private bundle, up to **192 MiB / 1,000 model calls**.
  The recorded local budget cap must be **at least the remote cap**. Actual
  spending may be lower; no minimum-spend percentage applies. Local testing uses your authorized model access.
- **Allowance:** the default is **20 model credits (USD equivalent) per Yukon account per
  rolling 24 hours**, with operator overrides. Unused allowance does not carry over:
  waiting two days does not permit a $40 run. Each funded remote run requires a
  budget cap of **at least $1**; actual spending may be lower. Each account may have one funded
  evaluation running at a time. Split the allowance across multiple sequential
  runs; each reserves its requested cap and returns unused funds after settlement. The live policy and account allowance take precedence.

See [funded submission instructions](docs/platform-funded-inference.md) for
matching rules, private review and budget reservations. Local results are never
imported as an official score; the remote evaluation starts fresh.

**Release compatibility:** `main` contains versioned problem manifests. Use the
[deployment compatibility notes](docs/deployment-compatibility.md) when targeting
the existing hosted evaluator; problem hashes must match its release.

## Develop

```sh
make check
```

This runs the public tests and builds, installs and checks a wheel in isolation.
It needs no model credential or Docker. See [development](docs/development.md)
for optional integration tests.

- [Documentation](docs/README.md): solver guides, API contracts and accounting.
- [Changelog](CHANGELOG.md): recent client changes and compatibility guidance.
- [Agent instructions](docs/agent-prompt.md): workflow for a solver's coding agent.
- [Architecture](docs/architecture.md): components, data flow and trust boundaries.
- [Submission state model](docs/submission-states.md): lifecycle, outcomes and identifiers.
- [Submission recovery](docs/submission-recovery.md): diagnostics, retries and escalation.
- [Scoring and budgets](docs/scoring-and-budgets.md): leaderboard comparison and spending.
