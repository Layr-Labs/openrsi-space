# Development

Use Python 3.11+ and uv. From the repository root:

```sh
uv sync --locked
make check
```

`make check` runs the public unittest suite, builds a wheel from fresh staging
files, installs it with locked runtime dependencies in a temporary environment,
and exercises the installed CLI, release catalogs, assets, starter and compatibility
imports. It does not use a model account, launch Docker or submit an evaluation.
Package installation may download build tools and locked dependencies.
The pull-request/push workflow runs the same check on Python 3.11 and 3.12.

For a focused test:

```sh
uv run python -m unittest discover -s tests -p test_module_boundaries.py -v
```

## Ownership

| Directory | Owns |
| --- | --- |
| `src/openrsi_space/contracts/` | Harness/evaluation schemas, accounting and result bindings |
| `src/openrsi_space/client/` | HTTP, login sessions, submission state and catalog downloads |
| `src/openrsi_space/cli/` | Arguments and command dispatch |
| `src/openrsi_space/harnesses/` | Starter generation, Docker build and smoke checks |
| `src/openrsi_space/challenge/` | Release loading, asset preparation and task assembly |
| `src/openrsi_space/problem-set/` | Pinned descriptions, resource catalogs, scaffolds and verifier bundles |
| `src/openrsi_space/integrations/` | Dungeness local execution and Yukon receipt submission |
| `src/openrsi_space/runtime/` | Container entrypoints copied into prepared runs |
| `tests/` | Public contracts, synthetic fixtures and regression tests |
| `script/` | Repository check and installed-package smoke test |

Small shared primitives and model-access helpers remain at package root. Old
module names such as `remote`, `tiers`, `problems`, `local` and `receipts` forward
to their owners for existing verifier releases. New implementation code imports
the owning package. Keep compatibility forwarding free of business logic.

Contracts must not import the HTTP client, CLI, execution machinery or integrations.
The CLI coordinates those layers; integrations may use client and contracts.
Challenge preparation may use Dungeness capability checks while challenge content
remains at stable package paths. See [architecture](architecture.md).

## Integration checks

For a real harness, follow [local evaluation](local-evaluation.md). Model-consuming
runs require model, spending-cap and credential authorization. A local check
does not issue an official receipt or establish a leaderboard improvement.

Changes to public request or receipt contracts need compatibility review. Preserve
existing records and document user-visible changes in the changelog.

## Public wording

The UI's “How it works” and “Participate” sections are the primary explanation for
solvers. Keep their benchmark description aligned with the opening of
[the challenge overview](overview.md): solvers submit their own harness, start and
control each run, and compare independently verified results. Local tests use
their authorized model access. Platform-funded remote runs, when enabled, require
private local evidence and use platform API access without a personal model
credential. Keep the local-budget-cap rule (not a minimum-spend rule) and source/evidence limits
consistent across human and coding-agent instructions. Describe account-facing
allowances, not internal fleet capacity.

For user-funded remote runs, explain authorized credential transfer, supported
login handoffs keeping refresh credentials local, cleanup of supplied access and
provider-terms responsibility. Do not imply that every remote run needs a personal key.
Keep provider-specific credential fields in the technical model-access guide.
