# Catalyst

[![Checks](https://github.com/Layr-Labs/catalyst/actions/workflows/check.yml/badge.svg)](https://github.com/Layr-Labs/catalyst/actions/workflows/check.yml)

Catalyst benchmarks research agent harnesses. Submit your harness using your own
model account, choose its spending and time limits, and compare independently
verified results on a public leaderboard. The initial challenge is **ecdsa.fail**.

This repository contains the solver CLI, challenge resources, accounting contracts
and Yukon receipt integration. Dungeness executes harnesses; the private
`catalyst-verifier` service manages official evaluations. Yukon hosts the UI.

## Get started

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --locked
uv run catalyst --help
uv run catalyst problem list
uv run catalyst harness create my-agent --executable --output .catalyst/my-agent
```

The starter makes no model calls. Follow the [solver guide](docs/solver-guide.md)
to test and submit a general-purpose harness. New submissions require public
harness source; review files before uploading. You authorize each paid run and
are responsible for complying with your model provider's terms.

**Release compatibility:** this branch preserves the hosted evaluator’s unversioned
problem identity. See the [compatibility notes](docs/deployment-compatibility.md)
before switching to `main` or changing problem manifests.

## Develop

```sh
make check
```

This runs the public tests and builds, installs and checks a wheel in isolation.
It needs no model credential or Docker. See [development](docs/development.md)
for optional integration tests.

- [Documentation](docs/README.md): solver guides, API contracts and accounting.
- [Agent instructions](docs/agent-prompt.md): workflow for a solver's coding agent.
- [Architecture](docs/architecture.md): module ownership and repository boundaries.
- [Challenge overview](docs/overview.md): rules, budgets and publication workflow.
