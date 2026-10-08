# ECDSA model-credit tiers

The initial official problem is `ecdsa.fail`, pinned in
`src/catalyst/problem-set/initial.json`. Compare harness source versions at
**20 and 200 normalized model USD credits, plus Best achieved**. At each tier, minimize the
best independently verified `avg_toffoli * peak_qubits` produced within that
allowance. Do not average scores across tiers or replace best performance with
the median of attempts. Retain each attempt and its complete curve.

## Decisions and open run strategy

The two checkpoints and Best achieved, native ECDSA metric, pinned credit pricing, and exclusion of
infrastructure cost are settled. One continuous run with checkpoints, up to a
solver-selected spending cap, remains **proposed, not confirmed**.
The $20/$200 values are comparison checkpoints, not a challenge-imposed spending
ceiling. Solvers may choose a larger spending cap and continue beyond them.
Independent tier runs are not selected either. The current code validates
records and projects explicit checkpoint evidence; it does not schedule either
strategy. If the strategy changes, give its execution conditions a new identity.

The harness's `evaluation.json` v3 requires a positive finite `max_model_credits`.
This is a spending authorization, separate from the comparison views. There is
no fixed $2,000 tier. Token/time limits can also end the run earlier. The runner
must seal any $20/$200 window it claims; a missing seal means that checkpoint is
unmeasured. Best achieved selects the lowest verified score across the complete
run and records its cumulative credits, even if the result arrived after both
checkpoints or above the former $2,000 threshold. It does not authorize unlimited
spending or predict when a future improvement will arrive.

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

The worker/gateway must reserve a conservative maximum charge before admitting
each request, including concurrent requests. It must stop admission and drain
or cancel in-flight work before capturing a candidate or sealing a checkpoint.
Do not release unaccounted streamed output to the harness. Reconcile cancellation
and retries before claiming `settled: true`; unknown consumption prevents a
score. The returned ledger contains final receipts, not outstanding reservations.
A charge crossing $20 cannot help the $20 tier, even if the request began below
$20. Budget overshoot beyond the funded cap rejects the scored record; never
clamp actual usage to the allowance.

These are worker requirements. This change implements decimal credit arithmetic
and result validation, not the live admission controller or checkpoint collector.

## Candidate capture and eligibility

The trusted controller assigns one strictly ordered sequence across usage
receipts, immutable candidate captures and tier seals. Events cannot share a
sequence or occur after `end_sequence`. At each capture it freezes the allowed
candidate paths, hashes their canonical contents, records settled cumulative
credits, and prevents submitted code from modifying the retained snapshot.
The independent verifier reads that exact digest in its own isolated workspace.
It reports `avg_toffoli`, `peak_qubits`, and their product. Candidate claims,
stdout, local timestamps and client scores are not evidence.

Verification can finish after the checkpoint closes. Eligibility uses the
trusted capture sequence and its fully settled usage, not verifier completion
time. A capture exactly at the credit allowance is eligible if it precedes the
seal. A capture after the seal is ineligible even if its credit total has not
changed. No backdating, interpolation or extrapolation is permitted.

For tier B, choose the minimum performance among independently verified captures
whose cumulative credits are <= B and whose capture sequence precedes B's seal.
Ties in performance may select the cheaper, then earlier, capture for display;
credit differences do not change the ECDSA performance ranking. Publish every
verified capture in the curve, including regressions and captures outside earlier
windows. Keep failed candidate artifacts and verifier failures in private traces.

Each tier has one explicit state:

| State | Meaning |
| --- | --- |
| `eligible` | A sealed window has a verified candidate; `best` identifies it. |
| `no_verified_candidate` | A sealed window has no eligible verified candidate. |
| `not_evaluated` | Within the funded cap but no checkpoint seal exists. |
| `not_funded` | Above this evaluation's authorized credit cap. |

Missing `best` values are null only in metadata. A valid scored evaluation must
have a verified candidate in the complete curve. Best achieved needs no fixed-tier
seal; it remains bound to settled usage, capture order, and the end of the run. A completed invalid evaluation
has an explanation and no score tuple. Worker/build failure is an execution
failure, not an invented circuit score. Repeated attempts remain distinct, with
source/build reuse independent of evaluation identity. The repetition/funding
policy is still open; these records do not assert equal total development spend.

## Yukon projection

Keep `schemaVersion: 1` and `editablePaths: ["submission"]`. Yukon's current
validator requires a finite score for every declared objective; partial
`[score20, null, null]` tuples and Infinity/sentinel scores are inappropriate.
Schema-v2 tracks also require non-overlapping editable paths.

Use two minimizing objectives: `[ecdsaPerformance, modelCreditsAtBest]`, where
the first is the best verified performance in the entire run and the second is
cumulative model credits at that candidate's capture. Authorized maximum credits
and final total usage remain separate. Missing $20/$200 observations stay in
metadata; they do not prevent a valid best-achieved score.

Yukon's generic Pareto frontier describes the best result/cost pair. The Catalyst
board ranks the selected view by performance: $20, $200, or Best achieved. A
later candidate can improve Best achieved without improving either sealed
checkpoint. Compare exact problem, pricing, model and execution conditions.
The archived Yukon preview needs adaptation to this contract before launch.

The local viewer is a development demonstration. It offers $20, $200 and Best achieved,
shows the best reported score and the full curve, and labels all local data as
synthetic or contributor-reported. Its legacy imported records do not contain
trusted seals and never qualify for official rankings.
