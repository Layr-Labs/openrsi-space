# Remote evaluation and submission

The private VM deployment and new direct Yukon backend retrieval path are
documented in [remote VM setup](remote-vm.md). The manifest now selects
`runner.provider: remote-verification`, with Pareto mode. The existing GitHub
workflow/OIDC path described below remains a legacy adapter; it is not the
current runner. Hosted Yukon still needs the provider release and configuration.

This repository implements the client/result contract, a persistent API,
and a separate Dungeness/Docker worker. The private remote deployment uses
explicitly provisioned account and Yukon consumer keys. It executes and
independently verifies pinned ECDSA candidates with model access disabled.
The [local integration check](local-evaluation.md) retains separate identity and
circuit fixtures. Automatic account/grant provisioning, provider access and
hosted Yukon registration remain pending. The remote MVP
runs the API and harness worker inside the existing `openclaw` VM. Reuse the VM
across jobs and isolate each run's workspace/containers. See
[architecture](architecture.md).

The only official problem is `ecdsa.fail`. Source/build identities are separate
from evaluation attempts. Official evaluations require an explicit finite model-credit cap; standalone local Dungeness experiments can still use development budgets
and remain contributor-reported.

## Standalone client

`catalyst remote` is the direct CLI for this service. The Yukon adapter in
`src/catalyst/yukon.py` delegates to the shared client in `src/catalyst/remote.py`;
it adds GitHub OIDC authentication and Yukon score-artifact output.

```sh
catalyst remote submit submission
catalyst remote status EVALUATION_ID
catalyst remote wait EVALUATION_ID
catalyst remote traces EVALUATION_ID

# Alternatively, enqueue and wait together:
catalyst remote submit submission --wait
```

`submit` defaults to `submission/` and returns JSON containing `evaluation_id`,
`request_id`, `source_digest` and `evidence_mode`. It uploads source and returns
after the service accepts the request. Progress goes to stderr; command results
are JSON on stdout.

Configure `CATALYST_EVALUATOR_URL` and authenticate using `CATALYST_API_TOKEN`
in the environment, or reuse Yukon login. Token precedence is
`CATALYST_API_TOKEN`, `YUKON_API_TOKEN`, the legacy Hilbert/Supabase environment
variables, then the Yukon configuration file. Tokens are never saved in job state
or sent as CLI arguments.

Keep the same global `--state` directory and endpoint when resuming:

```sh
catalyst --state /path/to/client-state remote wait EVALUATION_ID
```

Pending operation keys live under `remote/pending/` and accepted sessions under
`remote/evaluations/<id>/` within that state directory. Sessions save the exact
request and endpoint, with private permissions, so `wait` works in a new process.
An interrupted or uncertain submission with unchanged inputs reuses its request
ID. Older pending requests under `yukon/pending/` are also resumed without
replacing their operation keys.

`wait` verifies all result bindings and accounting, saves private traces,
`judgment.json` and `verification.json`, then exports the reference to the
original submission directory. If source or evaluation configuration changed
during execution, it retains the old evaluation's artifacts and refuses to
export a stale reference. Stopping a local wait does not cancel remote work.

Catalyst and Yukon share pending state: `yukon run` can finish a request first
queued through the standalone command with the same inputs. A new `submit`
after a successful `wait` deliberately creates a new attempt. To use a completed
direct evaluation in Yukon, proceed to `yukon submit` with its saved reference.
GitHub Actions cannot enqueue through the standalone command; its adapter
retrieves an existing result using `/submissions`.

## Request bindings and authentication

`submission/evaluation.json` v3 contains exactly:

```json
{
  "schema_version": 3,
  "llm_access": {"grant_id": "grant_example_only"},
  "model": {"provider": "openai", "name": "gpt-5.6-sol"},
  "max_model_credits": 20,
  "limits": {"max_model_tokens": 100000, "max_seconds": 900}
}
```

The grant is non-secret and server-authorized. Renewable credentials stay local;
temporary provider access travels over a separate private authenticated channel.
No provider token is sent by this bridge. A vault or reverse proxy is not an
initial requirement. The starter grant is empty so an unconfigured run fails
before network use.

Hash executable source with Catalyst's canonical per-file SHA-256 manifest,
including the Dockerfile, code, dependencies, instructions and knowledge.
Exclude `evaluation.json` and `verification.json` from the source/build context.
Bind the evaluation independently to that source digest, immutable server image,
ECDSA commit/problem-set digest, model/credit-cap/limits/config digest, pricing digest,
policy digest and authenticated owner. Retain pinned base images, toolchains,
Dungeness and builder identities in server provenance.

Configure `CATALYST_EVALUATOR_URL` as the trusted HTTPS endpoint. Loopback HTTP
exists for local testing. Refuse redirects. Local requests use the existing
service token or existing Yukon login token; validate it server-side and resolve the owner without trusting
client identity fields. Workflow requests use GitHub OIDC with audience
`catalyst-evaluator`. Validate issuer/signature/audience/repository/workflow/ref/
SHA/run claims, then bind the request to the exact queued Yukon submission and
its owner. GitHub identity alone cannot authorize another user's result or grant.

## HTTP contract

`POST /evaluations` accepts:

```text
protocol: "catalyst-evaluation-v3"
request_id: stable UUID
source: {digest, archive_base64}
evaluation: configuration above
problem_set: trusted initial ECDSA definition
pricing: complete pinned reference schedule
judge: {policies: {scoring, validity}, fields: {scores, validity}}
context: {kind: "yukon-solver"}
evidence_mode: "remote"
```

The API checks its own trusted problem, pricing and policy pins; client copies
cannot redefine the challenge. Validate source independently, authorize access
and limits, persist the job before acknowledging `{request_id, evaluation_id}`.
The same account/key/payload returns the same job. A changed payload under the
same key fails. The worker on the existing VM executes builds in separate
workspaces/containers, outside the API process. Persist results before cleaning
up each job; do not provision or destroy a VM for an evaluation.

`GET /evaluations/{id}` returns these bindings:

```text
protocol, evaluation_id, request_id, source_digest,
evaluation_config_digest, problem_set_digest, policies_digest, pricing_digest,
evidence_mode,
status: queued | building | running | verifying | completed | failed | cancelled
```

A completed result adds `valid`, `reason`, `trace_available`,
`build: {id, image_digest}`, and `observations`. Each ECDSA observation contains:

```text
problem_id: "ecdsa.fail"
problem_commit: pinned commit
pricing_digest: canonical pricing SHA-256
normalized_model_usd: total settled model credits (including usage after best result)
end_sequence: last trusted controller sequence
usage: [{sequence, request_id, settled: true,
         tokens: {input_tokens, output_tokens, cached_read_tokens, cache_write_tokens}}]
checkpoints: [{budget_tier, sequence, settled: true}]
curve: [{candidate_digest, verified_candidate_digest, captured_sequence,
         settled: true, verified: true, normalized_model_usd,
         avg_toffoli, peak_qubits, performance}]
```

All sequences share one controller-assigned order. Usage receipts are unique,
ordered and final. Input counts include cache subsets; output includes reasoning.
The validator recomputes credits using decimal arithmetic and requires each
candidate's cost to equal settled cumulative usage before capture. The independent
verifier must attest the exact captured digest and product metric. Seal order,
funding and settled usage are checked. Only captures before a tier's seal can
count. See [tier accounting](tier-accounting.md) for in-flight requests, inclusive
boundaries, missing tier states and full-curve retention.

The result is trusted because it is fetched from the authorized evaluator and
bound to its immutable records; `verified` and `settled` flags in client JSON
would not constitute proof. The local worker constructs its ledger from
Dungeness gateway receipts, reconciles terminal usage and captures a frozen
candidate after the harness stops. It seals eligible terminal windows only;
it does not invent captures for tiers crossed earlier. Runtime checkpoint
collection for official ECDSA runs is still pending. Continuous runs versus
independent tier runs remains open.

A valid scored result requires one ECDSA observation with a verified candidate. An invalid result needs an explanation; partial evidence may remain.
Build/worker failure yields no judgment, while private evidence stays available.

`GET /evaluations/{id}/traces` returns an authenticated private ZIP. The client
stores it without unpacking or executing it, with a 64 MiB download bound; retain
complete evidence server-side. Store source snapshots, candidate captures, failed
verifications, model usage and sanitized traces. Owner authorization and secret
redaction are required. Raw traces never enter the public GitHub artifact.

`POST /evaluations/{id}/submissions` receives the current source/configuration,
problem/pricing/policy pins and GitHub context, with no new evaluation request ID.
Authorize the queued submission and evaluation owner, compare against the actual
stored archive and immutable result, then return that existing result. Do not
start builds, model calls or another paid run. Workflow retries are safe.

The local v2 `verification.json` records evaluation/source/config/problem/policy/
pricing/image identities. It is a public reference, not an attestation. Changed
source, model, tier, limits or prices require new evidence. Uncertain initial
POSTs reuse their operation key; deliberate repeats create distinct jobs.

## Public judgment and remaining work

Public scores are `[best_verified_performance, model_credits_at_that_capture]`, matching the
two finite minimizing objectives in `benchmark.json`. The second coordinate is cumulative credits at the best verified capture.
The spending cap and terminal usage remain separate metadata. Missing tier results occur only in metadata,
never within Yukon score tuples. Invalid results use `scores: null`.

Metrics retain source/build/image/evaluation IDs, exact model, limits, credit cap,
pricing/config/problem digests, full verified curves and both checkpoint states and Best achieved.
The allowlist excludes private grants, usage request identifiers and raw traces.
One schema-v1 benchmark owns the shared `submission/` path; tiers are not tracks.
The archived Yukon board still needs an adapter to these tier summaries.

Before launch connect the existing local API/worker to live Yukon/OIDC identities
and queued submissions, and temporary provider access and renewal for ECDSA
research runs. Add runtime checkpoint capture and credit reservations, configure
job cleanup and private artifact retention on the existing VM, and complete
hosted registration. The measured local ECDSA baseline uses zero model credits;
it cannot substitute for a hosted, authenticated evaluation. No fabricated
baseline or local-score fallback is used.
