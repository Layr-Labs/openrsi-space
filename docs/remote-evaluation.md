# Remote evaluation and receipt retrieval

The current integration uses **unmodified Yukon**, its `github-actions` runner,
and the challenge-owned `.github/workflows/benchmark.yml`. See the
[complete end-to-end guide](github-actions-e2e.md) for deployment, registration,
network setup and commands. No custom Yukon provider is required.

## Standalone client

`catalyst remote submit HARNESS_DIRECTORY --wait` sends source to Catalyst and
waits for independent verification. It writes `verification.json` beside the
harness and retains private traces under `.catalyst/remote/`. An interrupted
wait resumes with `catalyst remote wait EVALUATION_ID`; submitting again after
completion requests a new evaluation. `status`, `wait` and `traces` never enqueue.
Use an operator-provisioned `CATALYST_API_TOKEN` and trusted
`CATALYST_EVALUATOR_URL`; provider credentials are separate and are not currently
accepted by the model-disabled MVP.

Develop harnesses in an ignored directory such as `.catalyst/my-harness` so
Yukon's trusted judge files stay unchanged. Copy the resulting receipt into
`submission/verification.json`, the only editable/submittable path. `yukon run`
now checks that receipt without running a harness. `yukon submit` uploads it using
Yukon's normal archive transport. Source and evaluation settings stay in Catalyst.

## Receipt-only Yukon submission

Yukon builds a candidate commit, opens the submission PR, and dispatches the
challenge workflow. The workflow authenticates with a GitHub OIDC token addressed
to `catalyst-evaluator`, then calls `POST /verifications/retrieve`:

```json
{
  "protocol": "remote-verification-receipt-v1",
  "reference": {"evaluation_id": "...", "schema_version": 2},
  "problem": {"id": "ecdsa.fail", "version": "<pinned problem-set SHA-256>"},
  "judge": {
    "policies": {"scoring": {"version": "..."}, "validity": {"version": "..."}},
    "fields": {"scores": true, "validity": true}
  }
}
```

The example abbreviates the receipt: send the entire service-issued object,
including its source/image/configuration/pricing/policy digests. The protocol
never accepts a claimed score or caller-supplied owner identity.

The service verifies GitHub's signature using the fixed GitHub JWKS endpoint,
issuer, audience, expiration, repository ID/name, workflow path, dispatch event,
ref and source SHA. Its private repository policy must explicitly enable the
challenge and pin the expected problem/version. For a submission ref
`refs/heads/submissions/<UUID>`, it reads the existing Yukon
`GET /api/submissions/<UUID>` endpoint to establish the real owner and benchmark.
Unknown, cancelled, cross-owner or cross-benchmark submissions fail closed.
Initial baseline dispatch instead requires an explicitly provisioned commit,
owner and already-verified receipt; it never fabricates a solver identity.

The verifier compares the receipt and requested problem/policies with its
retained evaluation. Success returns `protocol`, `reference`, `problem`, `judge`,
`artifact: {kind: "harness-source", sha256: "..."}`, and `judgment`. The client
checks those bindings and requested Pareto fields before writing the authoritative
score artifact. The artifact includes `metrics.remoteVerification` with the
problem/version and actual evaluated harness digest. Yukon records that artifact
through its existing GitHub Actions/Pareto path. Retrieval never starts a job.

Local preview uses the same endpoint with the solver's provisioned Catalyst key;
it authorizes only that owner's receipt and creates no workflow-publication record.
GitHub workflows cannot use local fixture evidence as official remote results.
Replays bind the original submission and GitHub run to the original evidence.

The direct-backend `remote-verification` provider and `/yukon/v1/retrieve`
prototype remain preserved for reference; they are not used by the current
manifest. The old `/evaluations/<ID>/submissions` workflow fixture adapter is
also retained for earlier local tests, not the hosted GitHub path.

## Request bindings and authentication

The harness's `evaluation.json` v3 contains exactly:

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
exists for local testing and private tunnels. Refuse redirects. Local requests
use a provisioned Catalyst service token; automatic Yukon login exchange is not
implemented. Resolve the owner without trusting client identity fields.
Workflow requests use GitHub OIDC with audience
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

The legacy fixture adapter `POST /evaluations/{id}/submissions` receives the current source/configuration,
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

The next integration milestone is a live GitHub dispatch and hosted Yukon
registration using the existing independently verified remote baseline. It uses
zero model credits and establishes the model-disabled MVP flow. Temporary
provider access and renewal for research runs, runtime checkpoint capture,
credit reservations and private artifact retention remain separate work.
No fabricated baseline or local-score fallback is used.
