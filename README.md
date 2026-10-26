# Catalyst

[![Checks](https://github.com/Layr-Labs/catalyst/actions/workflows/check.yml/badge.svg)](https://github.com/Layr-Labs/catalyst/actions/workflows/check.yml)

Catalyst is a benchmark for research agent harnesses. You submit your own
harness, using your own model account, to run in a controlled environment on
Catalyst's servers so that its performance can be independently verified and
compared with others on a public leaderboard.
The initial challenge is **ecdsa.fail**.

This repository contains the solver CLI, challenge resources, accounting contracts
and Yukon receipt integration. Dungeness executes harnesses; the private
`catalyst-verifier` service manages official evaluations. Yukon hosts the UI.

## Get started

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --locked
uv run catalyst --help
uv run catalyst --version
uv run catalyst problem list
uv run catalyst harness create my-agent --executable --output .catalyst/my-agent
```

The starter makes no model calls. Follow the [solver guide](docs/solver-guide.md)
to build a general-purpose harness, [test it locally with Dungeness](docs/local-evaluation.md),
then submit it for an official evaluation. Docker is needed for local integration tests. New submissions require public
harness source; review files before uploading. You authorize each paid run and
are responsible for complying with your model provider's terms.

`remote submit` reuses a matching completed local run. Use `--local-run PATH`
for records elsewhere, or explicitly `--skip-local-check` if testing is skipped.

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
- [Architecture](docs/architecture.md): module ownership and repository boundaries.
- [Challenge overview](docs/overview.md): rules, budgets and publication workflow.
