# Funding, evidence and scoring

## Local access and remote eligibility

| Stage | Model access | Who pays / authenticates |
| --- | --- | --- |
| Local test | Existing subscription or supported API | Solver's authorized login/key and allowance |
| Remote verification | Platform OpenRouter account | Eigen Labs pays; Yukon identifies the solver |
| Dashboard / optional receipt publication | No inference | Results appear automatically; optional Yukon publication uses the solver's login |

Subscription evidence qualifies for supported model equivalents. For example,
`openai-chatgpt/gpt-6-astra` can match `openrouter/openai/gpt-6-astra`, and
`claude-subscription/claude-opus-5-5` can match `openrouter/anthropic/claude-opus-5.5`.
The live `local_evidence_models` mapping in `remote funding-policy` is authoritative;
unlisted pairs require an exact provider/model match. Its top-level `providers`
list restricts remote funding, not local access. The unchanged harness must
support both routes; model equivalence does not translate API requests.

Every new submission requires ended local evidence with:

- Matching source, problem, model/equivalence and reasoning settings.
- A recorded local budget cap at least equal to the remote cap. **Local cap $2,
  actual spend $1.73 → remote $2 is eligible.** There is no minimum-spend percentage.
- At least one model exchange and complete responses and settled accounting for
  every recorded request. Failed/cancelled runs can qualify; prepared, running,
  zero-call or incomplete runs cannot. A valid local circuit is not required.
- At most 1,000 model calls and 192 MiB in the private exported bundle.

Use `--local-run PATH` or matching records discovered in client state. A changed
harness needs matching new evidence. Older exports missing the cap can be
re-exported from an unchanged original record that contains it; never invent a
cap or modify evidence. These checks establish consistency, not cryptographic
proof of historical execution. There is no skip flag or evidence exemption.

Evidence includes model exchanges, accounting and evaluation events, separately
from public source. It excludes login files and arbitrary filesystem archives,
is scanned for credentials, and is reviewed privately by a third-party LLM.
Review it for personal information before authorizing upload.

## Allowance and reservations

`remote funding-policy` is public. Authenticated `remote funding` reports your
rolling 24-hour allowance, reservations, settled usage, remaining amount and next
settled-charge expiry, including account overrides. Neither starts inference.

The default is **$20 per account per rolling 24 hours**, with a **$1 minimum run
cap** (`funding_budget_too_low` below that). Unused allowance does not accumulate.
Multiple sequential runs are allowed; only one funded evaluation can run per
account at once. Changing keys does not reset the allowance. Live policy,
enrollment, global capacity and upload/screening limits also apply.

New submissions check allowance before preparing/uploading evidence; admission
makes the final atomic reservation. The requested cap is reserved against your
account, without adding the platform's internal buffer. Screening/build failures
before inference release it. Known charges settle and unused funds return;
uncertain usage retains its hold and does not automatically expire. Microcredits
use 1,000,000 per USD equivalent.

An unchanged saved request bypasses the early balance check because it may already
hold funds. Retrying preserves request identity and reuses retained evidence,
even with `--local-run` supplied again. Missing/expired evidence can be exported
again from retained records without fresh inference. Observe `retry_after_seconds`;
the client does not automatically start a new paid attempt.

## Models and accounting

Choose an exact funded model advertised by policy. The service validates and pins
pricing; unknown models, automatic routing and unsupported charges are rejected.
Respect any deployment-specific `models` restriction. Use `--platform-funded`
without personal credential flags, and assigned gateway routes inside the harness.

OpenRouter settlement uses reported request charges (`billed_usd`). Reference-price
`normalized_usd` is retained separately for comparison and as an additional
conservative ceiling. Other local providers use their supported normalized
accounting. Subscription credits are not a cash charge or remaining plan allowance.

Before forwarding each request the gateway reserves for input/output. Long history
or a large output limit can cause a rejection while funds remain. A rejected
reservation is not a provider charge: inspect diagnostics and reduce the request,
rather than repeatedly sending it unchanged. Already admitted calls can exceed a
reservation/cap; unresolved charges retain their hold. See
[parallel accounting](generic-harnesses.md#parallel-accounting-and-evaluation).

For admission errors and safe retries, use [Troubleshooting](submission-recovery.md).
A scanner correction or upload failure alone does not require a new local run.

## Scoring and budget views

ECDSA minimizes **average executed Toffoli gates × peak qubits**. Only independently
verified candidates receive official scores. Compare identical problem versions,
pricing and scoring policies; harness stdout and local claims are not official results.

Each chart line shows one run's best verified score so far against cumulative
model credits. Select a run to see individual candidate evaluations as dots,
including ties and worse scores. For comparison budget B, choose the lowest verified
score at credits ≤ B; ties prefer fewer credits, then earlier observation order.
Best overall uses the full history. Missing points mean no verified result within
that budget, not zero score. A cheaper run may qualify for a larger view without
inventing additional observations. Changing a view never starts inference.

The result contract records $10/$20/$50/$100 views and best overall; the UI may
show a subset. Credits at the best result and total run spending are distinct.
All models/workers share the cap. Accounting includes consumed retries, failed
experiments and calls after the best candidate. Input, output/reasoning, caches
and supported long-context rates use the retained schedule without double counting.
Builds and verification infrastructure are separate from model credits.

History includes ties and regressions. Pending model usage settles before a point
is finalized, potentially raising its cumulative cost. Final verification checks
the saved terminal candidate at full run cost; a repeated score is not a fresh
improvement. An earlier verified candidate can remain best.

Overshoot is accepted only under the recorded admission policy: charged calls
must have started before settled spending exhausted the cap. Older results retain
their original policy. Never reduce costs to fit a budget view. Missing usage or
unsupported pricing cannot establish a verified score. See [reference pricing](generic-harnesses.md#reference-prices-for-declared-models).

Yukon receives best verified performance and credits at that result; full history,
models, cap and total usage remain separate. No observations at every budget are
required. Receipt publication preserves original identities and starts no research;
see [artifacts and publication](artifact-sharing.md).
