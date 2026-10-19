# ECDSA model-credit tiers

The initial official problem is `ecdsa.fail`, pinned in
`src/catalyst/problem-set/initial.json`. Compare harness source versions at
**10, 20, 50 and 100 normalized model USD credits, plus Best achieved**. At each tier, minimize the
best independently verified `avg_toffoli * peak_qubits` produced within that
allowance. Do not average scores across tiers or replace best performance with
the median of attempts. Retain each attempt and its complete curve.

## Spending caps and display budgets

Each evaluation is one Dungeness run with the solver's positive finite
`max_model_credits`. The solver may spend less than $10 or more than $100.
Token/time limits can also end the run. There is no $2,000 comparison tier.

**Within $10**, **Within $20**, **Within $50**, **Within $100**, and **Best overall** are views over the saved
verified curve. A $5 run qualifies for all four budget views. No funded-tier flag,
checkpoint seal, new run, interpolation or extrapolation is needed to select a
view. Spending authorization and total usage remain separate from credits at
the best result.

## Trusted accounting

`src/catalyst/problem-set/pricing.json` is the pinned reference schedule, copied
from Dungeness commit `506890937d75b659db714d3e02ea3d3cec3a1451`. Its canonical
JSON SHA-256 is included in requests, result bindings, receipts and public
metrics. Editing prices creates a different comparison policy identity; never
silently reprice historical evaluations. The API must use its own trusted copy
and reject client-provided overrides. These rates need no live provider lookup.
They are reference credits, not a claim about current billing prices.

Meter every model request in the run across all harness processes, including
failed experiments, retries with consumed tokens, and usage after the best
candidate. Input tokens include cache-read and cache-write subsets; output
includes reasoning tokens. Charge each bucket once. Apply the published
long-context tier to the entire request when its threshold is exceeded. Unknown
models, missing token counts, negative counts, duplicate request receipts, and
unsupported nonzero pricing buckets fail closed. Subscription routes use the
same reference prices as their corresponding API route; billed USD can be
unknown. Infrastructure, builds and verifier compute are separate records.

The first contract supports one exact provider/model per evaluation. Multi-model
harnesses need a later per-request model/authorization extension; do not accept
unmetered secondary model calls. A pricing entry is not a claim that its provider
authentication adapter has already been implemented.

Dungeness owns admission, metering and the usage ledger. Catalyst recomputes
credits from its settled receipts using the pinned schedule. Unknown consumption,
unsettled requests and token-limit overruns prevent a valid score. Under validity
policy `ecdsa-trusted-checkpoints-v3`, final in-flight responses may exceed the
credit cap only when every charged request has trusted admission evidence showing
it started before settled spending reached the cap. The gateway blocks new calls
after exhaustion; already admitted concurrent responses may finish. The worker
records `admitted_after`, the last settled charged request ID at each gateway
request event (or null before any settlement), from canonical gateway history.
Missing admission evidence retains the strict cap. Explicit v2 judgments retain
their original strict cap and policy digest; historical receipts are not rewritten. A request crossing $20 cannot benefit the $20 view even
if it began below $20. Never clamp an overrun to the allowance.

## Existing evaluator history

The private service adapter reads Dungeness's existing
`usage/events.jsonl`: trusted `evaluator / evaluation.completed` records with
`operation: score`, `status: ok`, candidate/source SHA-256, Toffoli count, peak
qubits, score and a cumulative usage snapshot. It checks that snapshot against
the canonical accounting order and retains every successful evaluation,
including ties and regressions. It does not install a new capture mechanism.

If a model request started before the evaluation but settled afterward, the
observation is charged at that settlement, including other usage settled by then.
This conservative rule prevents streamed output from producing an artificially
cheap score. Fallback evaluator-completion records without a canonical gateway
sequence cannot establish a budget observation; they are omitted and counted in
private history diagnostics. Unordered gateway accounting and malformed or
contradictory canonical records fail closed.

The worker also freezes the terminal candidate and independently reruns the
pinned ECDSA verifier with no network. That final point remains in the curve at
full run cost, even when an earlier evaluator result is better. The two digest
formats are labeled: Dungeness hashes module-relative contents; Catalyst hashes
its canonical file map. They are not interchangeable identifiers.

For budget B, select minimum performance among observations at cumulative
credits <= B. Break ties by fewer credits, then earlier order. A result exactly
at B qualifies. Each view is `eligible` or `no_verified_candidate`; the latter
has `best: null` in metadata, never a fabricated score. Legacy seals can still
be read and validated but do not restrict eligibility.

Historical receipts and already-published Yukon results remain immutable. A UI
can read a legacy final-only receipt, but cannot invent its missing intermediate
history. Re-exporting a retained old run needs an explicit new publication; it
does not silently rewrite the old receipt.

## Cheat screening

See [screening policy](cheat-filter.md). Harness source is screened before build;
every new intermediate ECDSA evaluation is screened before invoking the pinned
scorer; the final frozen candidate is screened before independent verification.
The filter is a conservative additional check, not proof against arbitrary
malicious Rust or a replacement for worker isolation.

## Yukon projection

Keep `schemaVersion: 1` and `editablePaths: ["submission/verification.json"]`. Yukon's current
validator requires a finite score for every declared objective; partial
`[score20, null, null]` tuples and Infinity/sentinel scores are inappropriate.
Schema-v2 tracks also require non-overlapping editable paths.

Use two minimizing objectives: `[ecdsaPerformance, modelCreditsAtBest]`, where
the first is the best verified performance in the entire run and the second is
cumulative model credits at that candidate's capture. Authorized maximum credits
and final total usage remain separate. Missing $10/$20/$50/$100 observations stay in
metadata; they do not prevent a valid best-achieved score.

Yukon's generic Pareto frontier describes the best result/cost pair. The Catalyst
board ranks the selected view by performance: $10, $20, $50, $100, or Best achieved. A
later candidate can improve Best achieved without improving an earlier
budget view. Compare exact problem, pricing, model and execution conditions.
The challenge UI reads this curve through the standard Yukon API; no Yukon backend patch is required.

The local viewer is a development demonstration. It offers $10, $20, $50, $100 and Best achieved,
shows the best reported score and the full curve, and labels all local data as
synthetic or contributor-reported. Its imported records have contributor-reported provenance and cannot qualify for official rankings.
