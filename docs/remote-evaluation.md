# Public remote evaluation contract

The public client and the private `openrsi-space-verifier` service communicate over
HTTPS. No private Python package, Dungeness checkout or server credential is
required to call the remote API. Funded solvers must retain evidence from a
matching local Dungeness run, even though the submission command itself does
not launch a local runtime. Extraction does not
change the existing wire protocols, evaluation IDs or receipts.

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
handoff is restricted to `POST /evaluations` and the exact
`POST /evaluations/<evaluation-id>/credentials` renewal route.

Solvers use their Yukon login or `YUKON_API_TOKEN`. `POST /auth/yukon` exchanges
that key for a temporary solver session using the solver-session protocol.
The service establishes ownership through its configured Yukon instance;
clients cannot assert another owner or choose the authentication issuer.

Model access is separate from Yukon authentication. Hosted runs are platform-funded
and receive no personal model credentials. Remote subscription-token submission
has been removed, including the remote `--codex-auth-file` option. API-key handoff
through `--provider-access-file`, the hidden prompt or stdin remains implemented
but is currently disabled on the hosted service. See [model access](live-models.md).

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
this evidence; there is no skip option or operator exemption. See [funded submission details](platform-funded-inference.md).

GitHub Actions uses a short-lived OIDC identity for receipt retrieval. That
identity authenticates the workflow; it is not the evaluation receipt and cannot
supply model access or create a paid run.

## Submit once and resume retrieval

See the [submission state model and recovery guide](submission-states.md) for
state meanings, identifiers and symptom-based recovery. Evaluation completion is
separate from Yukon publication; resuming retrieval does not restart research.

`POST /evaluations` accepts the versioned request constructed by
[`remote.py`](../src/openrsi_space/remote.py):

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
assigned automatically; see [artifact sharing](artifact-sharing.md) for the limited
participant license under the OpenRSI Terms of Service and existing third-party rights.
Source is published automatically after the run stops and credential screening
passes. Trace publication is disabled.
Older clients that omit this field must upgrade before starting a new evaluation.
Historical stored requests remain readable and are not retroactively published.

`openrsi-space remote status ID` reads `GET /evaluations/ID`.
`openrsi-space remote wait ID` waits for completion and validates the returned bindings.
These commands do not enqueue work. States include queued, building, running,
verifying, awaiting_credentials, completed, failed and cancelled. Renew temporary
access for an owned job before provider execution with `remote renew-access`.
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

### Troubleshooting an owned run

```bash
openrsi-space remote diagnostics EVALUATION_ID --output diagnostics.json
```

This reads `GET /evaluations/EVALUATION_ID/diagnostics` using your Yukon login;
it does not start a run or require model credentials. The saved file has private
permissions. Owner status responses also include this versioned diagnostics
report, and `remote wait` prints failure categories and the latest available
candidate evaluation event to stderr.

The report distinguishes runtime observations, harness-reported errors, and
independent verification results. For example, `HARNESS_EXIT_NONZERO` with a
harness-reported `FileExistsError` identifies a harness crash, while
`CANDIDATE_REJECTED` identifies a candidate that failed verification. Both may
occur in the same run. A completed run does not necessarily contain a valid
candidate. The report includes at most 50 recent evaluator events; these are
observed evaluations, not a complete history of the harness's attempted work.

Reports are troubleshooting information, **never score or receipt evidence**.
They exclude raw logs, model responses, credentials, private server paths and
hidden test inputs or expected outputs. Trace downloads remain disabled.
Missing information is unavailable, not evidence that a step succeeded or never
ran. Older runs can only show information retained at execution time. An older
service without this endpoint needs an operator update.

An interrupted model stream is different from a harness or candidate failure.
`MODEL_USAGE_UNAVAILABLE` means the gateway could not obtain trusted usage for a
particular request. Its report includes the request ID, duration and observed
failure category when retained. A category identifies where the error was observed,
not necessarily who caused it; historical failures may remain `undetermined`.

The gateway continues draining the same upstream stream after a harness disconnect
so it can capture late usage. A separate later request reports its own usage; it
does not settle the missing request. Under the current policy, incomplete accounting
blocks a verified receipt even when an earlier candidate passed. Reported credits
then exclude unknown usage and must not be interpreted as a complete total or a
zero charge for the interrupted request. Passing local tests cannot guarantee that
a remote provider connection will complete. The operator should investigate the
gateway event, while the solver can review harness error handling independently.

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

Source, problem, configuration, pricing and policy digests are bound to the result.
A completed result contains the independently verified candidates and Dungeness's
settled usage. The public validator checks the accounting and candidate bindings;
claims in arbitrary local JSON do not constitute official evidence.

## Receipts and Yukon

Opt into [client-side automatic Yukon publication](automatic-publication.md) with
`remote submit --publish-to-yukon`. The CLI waits for verification and publishes
using your local login; `remote wait` resumes the saved choice after disconnection.
The verifier retains no Yukon key between requests. Publication retries never restart
research. The manual receipt workflow below remains available.

The client writes the complete service-issued `verification.json` beside the
submitted harness. Create `submission/` and copy it into `submission/verification.json` in the
challenge checkout. This is the only Yukon-editable path. It contains immutable evidence
references, not credentials and not a score chosen by the submitter.

`yukon run` invokes `openrsi-space yukon-run` and retrieves the retained result.
`openrsi-space yukon-submit` submits the receipt through stock Yukon and binds the
resulting job through `POST /verifications/yukon-bind` with protocol
`yukon-execution-binding-v1`. The service authenticates the Yukon job and checks
its benchmark and owner. Bindings are immutable and retryable. `openrsi-space yukon-bind`
can finish a previously accepted submission without submitting it again.

The hosted Yukon workflow retrieves the retained verified result using its own
authentication. Solvers do not need to construct workflow credentials or call the
workflow-only retrieval endpoint. Keep receipts unchanged and publish from the
account and benchmark associated with the evaluation. Modified or mismatched
receipts are rejected; publication never trusts a score supplied in a note.

See [Yukon publication](submission-states.md#publish-a-verified-receipt) for the workflow and recovery rules.

## Scores, curves and artifacts

Yukon's two minimizing coordinates are
`[best_verified_performance, model_credits_at_that_capture]`, where performance
is `avg_toffoli × peak_qubits`. Both coordinates must be finite. An invalid result
has no score tuple and includes a reason.

Metrics retain the complete verified curve, model identities, run cap, total
usage and provenance. The $10/$20/$50/$100/Best views select from that evidence;
a later candidate cannot improve an earlier budget view. Missing budget results
are explicit metadata, never invented Yukon tuple values. See [accounting](scoring-and-budgets.md).

Owners can download harness source and add an authorized source license. New
harness source must remain public; solvers cannot make it private.
Traces are retained internally for verification and debugging;
trace and complete-bundle downloads are unavailable, including to the run owner.
See [downloads and sharing](artifact-sharing.md).

`trace_available` in retained results attests that the verifier kept internal
evidence; it does not advertise a download. Upgrade older clients before using
`remote wait`: older versions attempted to download traces automatically.

The public contract is defined by this guide and the public client validators.
Service deployment, queue administration, corpus operations and screening
implementation belong in `openrsi-space-verifier`.

## Rejected submissions without an evaluation ID

The CLI displays safe admission diagnostics for HTTP errors, including the
server correlation ID, rejection code, failing field and known validation reason.
Where available, it includes a validated expected protocol/mode/problem digest.
It never prints the raw response body or arbitrary server error text.

If an evaluation submission receives an HTTP error, the latest sanitized report
is saved at `<state>/remote/diagnostics/<request-id>.json` with private permissions.
The saved request, source and settings are preserved. This report contains no
source archive, authorization header, model credential or raw response body.
A malformed/non-JSON edge error can still retain `edge_id` from the response header.

For support, provide that report and the time of the attempt. The operator can
look up durable admission records without an evaluation ID. A rejection before
job creation does not have a run to fetch. Diagnose a 400 before retrying; do not
change the request ID to try to bypass it. Updating the CLI does not recover an
error body discarded by an older version and does not submit anything by itself.

### Diagnose an existing run

`openrsi-space remote diagnostics EVALUATION_ID` includes separate execution,
verification and publication outcomes. A publication failure does not require
another funded evaluation: retry publication with the retained verified receipt.

To download your sanitized harness stdout/stderr and its completeness report:

```bash
openrsi-space remote logs EVALUATION_ID --output run-logs.zip
```

This uses your existing Yukon authentication and never starts inference. Logs
are private, bounded diagnostic output; the ZIP reports missing, partial or
truncated capture. Full internal traces and raw operator logs remain unavailable.
A server release mismatch is an operator issue; keep your existing local evidence
and retry after the operator repairs the deployment.
