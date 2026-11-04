# OpenRSI through unmodified Yukon

OpenRSI uses Yukon's stock `github-actions` runner and Pareto mode. No custom
Yukon backend patch is needed. The public challenge repository owns
[`benchmark.json`](../benchmark.json) and
[the workflow](../.github/workflows/benchmark.yml).

## Workflow

1. The solver submits source and authorized temporary model access directly to
   the remote service through the `openrsi-space` CLI.
2. The service returns a receipt for independently verified retained evidence.
3. The solver submits only `submission/verification.json` to Yukon.
4. Yukon creates a candidate commit and dispatches the repository's workflow.
5. The workflow authenticates with GitHub OIDC and retrieves the existing result.
6. Yukon records the returned score and full metrics; the UI reads those official
   results. The workflow does not start another paid evaluation.

Follow [the solver guide](solver-guide.md) for commands and
[the public contract](remote-evaluation.md) for authentication and result bindings.
A local `yukon run` checks an owned receipt before submission. Hosted dispatch
additionally exercises GitHub identity and the real Yukon execution binding.

## Challenge author setup

The Yukon GitHub App needs access to this challenge repository, and the benchmark
must be registered in the intended Yukon environment. Preserve its identity when
updating source. A newly created GitHub repository has a different numeric ID,
which requires coordinated OIDC authorization in the private verifier service.

The workflow needs internet access to the service's HTTPS endpoint. Configure
`OPENRSI_EVALUATOR_URL` as a GitHub Actions repository variable. The URL is not a
secret; using a variable lets the service migrate without editing solver source.
The workflow needs `id-token: write` to request GitHub OIDC. It does not need the
solver's Yukon key or model credentials, and it does not use SSH to run verification.

Service authorization and baseline provisioning are operator work in the private
`openrsi-space-verifier` repository. The public workflow has no copy of that service
or its anti-cheat implementation. Receipt retrieval must fail if the service is
unreachable or rejects the binding; there is no local-score fallback.

Receipt publication uses the receipt's original problem hash, not the installed
client's default problem release. The verifier must authorize that problem or
the exact historical receipt. A v3 workflow can validate a retained v2 receipt
under v2's stricter final-spend rule; it records both original and benchmark
policies in the metrics. Unknown policy changes and v3-to-v2 downgrades fail.
This does not change the evaluation's problem, budget, pricing, or stored result.

Updating the repository alone does not move Yukon's pinned benchmark source.
Operators must coordinate the benchmark reorg with verifier authorization and
the exact baseline revision. Revalidation retrieves retained receipts and does
not start another paid research evaluation. New solver publications still use
the normal `openrsi-space yukon-submit` / `openrsi-space yukon-bind` flow.

## Validation

The public test suite checks receipt validation, finite Pareto scores and the
client's idempotent request handling. The private service suite additionally
checks signed OIDC authentication, owner/problem/source binding, replay handling,
worker lifecycle and real HTTP client/server interactions with local fixtures.

A hosted smoke test requires a valid retained receipt and a registered benchmark.
It tests retrieval without purchasing another research run. Source extraction
alone does not perform that hosted test or change the deployed service.
