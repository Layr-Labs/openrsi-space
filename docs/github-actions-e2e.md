# Catalyst through unmodified Yukon

Catalyst uses Yukon's stock `github-actions` runner and Pareto mode. No custom
Yukon backend patch is needed. The public challenge repository owns
[`benchmark.json`](../benchmark.json) and
[the workflow](../.github/workflows/benchmark.yml).

## Workflow

1. The solver submits source and authorized temporary model access directly to
   the remote service through the Catalyst CLI.
2. The service returns a receipt for independently verified retained evidence.
3. The solver submits only `verification.json` to Yukon.
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
`CATALYST_EVALUATOR_URL` as a GitHub Actions repository variable. The URL is not a
secret; using a variable lets the service migrate without editing solver source.
The workflow needs `id-token: write` to request GitHub OIDC. It does not need the
solver's Yukon key or model credentials, and it does not use SSH to run verification.

Service authorization and baseline provisioning are operator work in the private
`catalyst-verifier` repository. The public workflow has no copy of that service
or its anti-cheat implementation. Receipt retrieval must fail if the service is
unreachable or rejects the binding; there is no local-score fallback.

## Validation

The public test suite checks receipt validation, finite Pareto scores and the
client's idempotent request handling. The private service suite additionally
checks signed OIDC authentication, owner/problem/source binding, replay handling,
worker lifecycle and real HTTP client/server interactions with local fixtures.

A hosted smoke test requires a valid retained receipt and a registered benchmark.
It tests retrieval without purchasing another research run. Source extraction
alone does not perform that hosted test or change the deployed service.
