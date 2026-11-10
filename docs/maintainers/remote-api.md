# Remote API contract

Solvers should use [Quickstart](../solver-guide.md). This reference is for client integrators.

## Authentication and model access

`OPENRSI_EVALUATOR_URL` selects the trusted HTTPS endpoint. The client refuses
redirects. Loopback HTTP is reserved for local fixtures.

The official client checks the TLS certificate chain, expiration and hostname
using Python/OpenSSL's default trust store before sending authorization headers,
model credentials or a request body. Keep your operating system and client CA
store current. A custom CA override changes which issuers the client trusts.
An expired, untrusted or wrong-host certificate stops the request; correct the
endpoint, certificate or trust store and retry the same saved request ID. Do not
disable certificate verification (`curl -k`, `verify=False`, or equivalent).

Custom clients must use HTTPS for the first credential-bearing request and refuse
redirects. An HTTP-to-HTTPS redirect cannot protect credentials already sent over
HTTP. Real model credentials are refused even on loopback HTTP. HTTPS model-token
handoff is restricted to `POST /evaluations`.

Solvers use their Yukon login or `YUKON_API_TOKEN`. `POST /auth/yukon` exchanges
that key for a temporary solver session using the solver-session protocol.
The service establishes ownership through its configured Yukon instance;
clients cannot assert another owner or choose the authentication issuer.

Model access is separate from Yukon authentication. Hosted runs are platform-funded
and receive no personal model credentials. Remote subscription-token submission
has been removed, including the remote `--codex-auth-file` option. API-key handoff
through `--provider-access-file`, the hidden prompt or stdin remains implemented
but is currently disabled on the hosted service. See [model access](../live-models.md).

Platform-funded requests instead use the non-secret grant
`evaluation.llm_access.grant_id: grant_platform_funded` and send no
`X-OpenRSI-Model-Token`. Discover availability, funded providers and any explicit model restrictions through
`GET /public/funding-policy`. Authenticated `GET /funding` reports the account’s
reservations and settled usage for the authenticated account.

For a funded submission, `POST /local-evidence` uploads a private
versioned local-evidence JSON bundle and returns its digest. Include that digest
as top-level `local_evidence` in the evaluation request. The bundle contains
recorded model exchanges, settled accounting and evaluation events, not arbitrary
local files. Source, problem and model settings must match. The numeric
`local_budget_cap_usd` field must come from the recorded local configuration and
be at least the requested remote cap; actual spending may be lower. The upload is limited
to 192 MiB and 1,000 model calls, separately from the public source ZIP.
The server screens it for secrets and performs bounded LLM readiness review; it
is not proof of full replay or authenticity. Every new funded submission requires
this evidence; there is no skip option or operator exemption. See [funded submission details](../platform-funded-inference.md).

GitHub Actions uses a short-lived OIDC identity for receipt retrieval. That
identity authenticates the workflow; it is not the evaluation receipt and cannot
supply model access or create a paid run.

## Evaluation requests

`POST /evaluations` accepts the versioned request constructed by
[`remote.py`](../../src/openrsi_space/remote.py):

```text
protocol: <service-reported evaluation protocol>
request_id: stable UUID
source: {digest, archive_base64}
local_evidence: private bundle digest for funded submissions
evaluation: declared models, spending cap, limits and non-secret access grant
publication: {harness: true, traces: false, license: null}
problem_set: pinned challenge definition
pricing: exact reference schedule
judge: requested score/validity fields and policy versions
context: {kind: yukon-solver}
evidence_mode: remote
```

The service validates its own trusted problem, pricing and policy definitions
against the request. It independently verifies the archive digest and authorizes
the owner and run limits. An acknowledged request returns `evaluation_id` and
`request_id`. Retrying the same account/request/payload is idempotent; changing
the payload under the same request ID is rejected. The client preserves uncertain
requests instead of issuing another paid run.

New requests must explicitly include `publication`. New submissions must set `publication.harness` to `true`; private source is rejected.
Traces remain internal. A source license is optional; leave `--source-license`
unset unless the user explicitly asks for one. No additional source license is
assigned automatically; see [artifact sharing](../artifact-sharing.md) for the limited
participant license under the OpenRSI Terms of Service and existing third-party rights.
Source is published automatically after the run stops and credential screening
passes. Trace publication is disabled.
Older clients that omit this field must upgrade before starting a new evaluation.
Historical stored requests remain readable and are not retroactively published.

`openrsi-space remote status ID` reads `GET /evaluations/ID`.
`openrsi-space remote wait ID` waits for completion and validates the returned bindings.
These commands do not enqueue work. States include queued, building, running,
verifying, completed, failed and cancelled. Missing or expired model access ends
the attempt with `MODEL_ACCESS_UNAVAILABLE`; it does not pause for credentials.
`remote cancel` requests cancellation; do not resubmit while cancellation is pending.

Pending status responses include owner-only `progress` from Dungeness's live
gateway summary: elapsed time, normalized credits, model requests, evaluation
count and the best recorded score. Requests include admitted attempts that may
still be in flight or fail; credits include only usage recorded so far. The
summary's age is provided so a quiet or slow request is not mistaken for fresh
activity. Before the gateway starts, usage is unavailable rather than reported
as zero.

`remote wait` and `remote submit --wait` print a progress line to stderr every
15 seconds and immediately on phase changes. Final JSON stays on stdout.
Live scores are **provisional**, not a verified receipt or evidence for Yukon.
Progress exposes no prompts, source, tool output, credentials or server paths.
Older services still work, with a periodic waiting message instead of metrics.

## Safe diagnostic events

Harnesses can optionally emit one compact JSON line to stdout when an error
occurs, before cleanup that might itself fail:

```json
{"event":"openrsi.diagnostic","schema_version":1,"stop_reason":"runtime_error","exception_type":"FileExistsError","location":{"file":"agent.py","line":81}}
```

Only recognized exception types and stop reasons are exposed. A location is
optional and must identify a relative source file in the submitted bundle.
Arbitrary messages and tracebacks are discarded. This is a best-effort projection
of retained runtime output, not a guaranteed live harness logging channel. Keep
detailed local logs for synthetic mechanics tests, including interrupted attempts
and restart recovery. Each remote evaluation must still begin with fresh memory
and its officially assigned resources.

See [Troubleshooting](../submission-recovery.md), [submission states](../submission-states.md), and [artifact/publication commands](../artifact-sharing.md) for result handling.
