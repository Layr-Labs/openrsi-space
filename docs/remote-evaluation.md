# Public remote evaluation contract

The public client and the private `catalyst-verifier` service communicate over
HTTPS. No private Python package, Dungeness checkout or server credential is
required by solvers or the challenge's GitHub workflow. Extraction does not
change the existing wire protocols, evaluation IDs or receipts.

## Authentication and model access

`CATALYST_EVALUATOR_URL` selects the trusted HTTPS endpoint. The client refuses
redirects. Loopback HTTP is reserved for local fixtures.

Solvers use their Yukon login or `YUKON_API_TOKEN`. `POST /auth/yukon` exchanges
that key for a temporary solver session using `catalyst-yukon-session-v1`.
The service establishes ownership through its configured Yukon instance;
clients cannot assert another owner or choose the authentication issuer.

Model access is separate from Yukon authentication. `--codex-auth-file`,
`--provider-access-file`, `--prompt-model-token` or `--model-token-stdin` explicitly
authorizes remote use of the solver's model account. The client sends temporary
access separately from the source archive and evaluation JSON over HTTPS.
Refresh credentials remain local. Access must not appear in receipts, source,
public results or retained traces. See [model access](live-models.md).

GitHub Actions uses a short-lived OIDC identity for receipt retrieval. That
identity authenticates the workflow; it is not the evaluation receipt and cannot
supply model access or create a paid run.

## Submit once and resume retrieval

`POST /evaluations` accepts the versioned request constructed by
[`remote.py`](../src/catalyst/remote.py):

```text
protocol: catalyst-evaluation-v3
request_id: stable UUID
source: {digest, archive_base64}
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

New requests must explicitly include `publication`. The CLI defaults to public
harness source, internally retained traces and no source license grant. `--private-harness`
opts out of public source; `--source-license` selects an authorized license.
Source is published automatically after the run stops and credential screening
passes. Trace publication is disabled.
Older clients that omit this field must upgrade before starting a new evaluation.
Historical stored requests remain readable and are not retroactively published.

`catalyst remote status ID` reads `GET /evaluations/ID`.
`catalyst remote wait ID` waits for completion and validates the returned bindings.
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

Source, problem, configuration, pricing and policy digests are bound to the result.
A completed result contains the independently verified candidates and Dungeness's
settled usage. The public validator checks the accounting and candidate bindings;
claims in arbitrary local JSON do not constitute official evidence.

## Receipts and Yukon

The client writes the complete service-issued `verification.json` beside the
submitted harness. Create `submission/` and copy it into `submission/verification.json` in the
challenge checkout. This is the only Yukon-editable path. It contains immutable evidence
references, not credentials and not a score chosen by the submitter.

`yukon run` invokes `catalyst yukon-run` and retrieves the retained result.
`catalyst yukon-submit` submits the receipt through stock Yukon and binds the
resulting job through `POST /verifications/yukon-bind` with protocol
`yukon-execution-binding-v1`. The service authenticates the Yukon job and checks
its benchmark and owner. Bindings are immutable and retryable. `catalyst yukon-bind`
can finish a previously accepted submission without submitting it again.

Yukon creates a candidate commit and dispatches the challenge-owned workflow.
The workflow presents its GitHub OIDC identity to `POST /verifications/retrieve`:

```json
{
  "protocol": "remote-verification-receipt-v1",
  "reference": {"schema_version": 2, "evaluation_id": "..."},
  "problem": {"id": "ecdsa.fail", "version": "<pinned problem-set SHA-256>"},
  "judge": {
    "policies": {"scoring": {"version": "..."}, "validity": {"version": "..."}},
    "fields": {"scores": true, "validity": true}
  }
}
```

This example abbreviates `reference`; always send the complete issued receipt.
The service checks the allowed workflow/repository, dispatched commit and actual
Yukon submission's owner/benchmark, then compares the receipt to retained evidence.
Unknown, modified, cross-owner or wrong-problem references fail. Retrieval does
not build a harness, run a model or accept a caller-supplied score.

Success returns the bound reference, problem, policy request, evaluated source
artifact digest and authoritative judgment. The workflow validates the response
before writing the score artifact Yukon collects. See
[`receipts.py`](../src/catalyst/receipts.py) and
[the GitHub integration](github-actions-e2e.md).

## Scores, curves and artifacts

Yukon's two minimizing coordinates are
`[best_verified_performance, model_credits_at_that_capture]`, where performance
is `avg_toffoli × peak_qubits`. Both coordinates must be finite. An invalid result
has no score tuple and includes a reason.

Metrics retain the complete verified curve, model identities, run cap, total
usage and provenance. The $10/$20/$50/$100/Best views select from that evidence;
a later candidate cannot improve an earlier budget view. Missing budget results
are explicit metadata, never invented Yukon tuple values. See [accounting](tier-accounting.md).

Owners can download harness source and change its visibility. New harness source
is public by default. Traces are retained internally for verification and debugging;
trace and complete-bundle downloads are unavailable, including to the run owner.
See [downloads and sharing](artifact-sharing.md).

`trace_available` in retained results attests that the verifier kept internal
evidence; it does not advertise a download. Upgrade older clients before using
`remote wait`: older versions attempted to download traces automatically.

The public contract is defined by this guide and the public client validators.
Service deployment, queue administration, corpus operations and screening
implementation belong in `catalyst-verifier`.
