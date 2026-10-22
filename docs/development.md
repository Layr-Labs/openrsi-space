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
| `src/catalyst/contracts/` | Harness/evaluation schemas, accounting and result bindings |
| `src/catalyst/client/` | HTTP, login sessions, submission state and catalog downloads |
| `src/catalyst/cli/` | Arguments and command dispatch |
| `src/catalyst/harnesses/` | Starter generation, Docker build and smoke checks |
| `src/catalyst/challenge/` | Release loading, asset preparation and task assembly |
| `src/catalyst/problem-set/` | Pinned descriptions, resource catalogs, scaffolds and verifier bundles |
| `src/catalyst/integrations/` | Dungeness local execution and Yukon receipt submission |
| `src/catalyst/runtime/` | Container entrypoints copied into prepared runs |
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

The private `catalyst-verifier` repository owns service and cross-repository tests.
Run them against this working tree before deploying a package-layout change:

```sh
# From catalyst-verifier, with its development environment installed:
CATALYST_PUBLIC_ROOT=../catalyst \
PYTHONPATH=src:../catalyst/src:tests:../catalyst/tests \
  .venv/bin/python -m unittest discover -s tests
```

Set `CATALYST_DUNGENESS` to a clean compatible Dungeness checkout to include the
optional compiler integration check. The verifier's `scripts/check-local-e2e.py`
exercises Docker execution, independent verification, receipts and Yukon with
synthetic fixtures; consult that script's `--help` for checkout paths. These checks
require the corresponding toolchains and do not belong in public credential-free CI.

For a real harness, follow [local evaluation](local-evaluation.md). Model-consuming
runs require explicit model, spending-cap and credential authorization. A local
check does not issue an official receipt or establish a leaderboard improvement.
