# Scores and model credits

The ECDSA objective is **average executed Toffoli gates × peak qubits**; lower is
better. Only independently verified candidates receive scores. Compare runs with
the same problem version and scoring policy; local results and harness-reported
numbers are not official scores.

## Spending caps and display budgets

A run has a positive finite spending cap and a time limit. An optional token limit
can also stop it. These limits authorize a run; selecting a leaderboard budget
only changes how its existing verified history is displayed.

For a comparison budget B, select the lowest verified score reached at cumulative
model credits **less than or equal to B**. Break ties by fewer credits, then earlier
observation order. Best overall uses the full verified history without a fixed
comparison budget. A shorter or cheaper run can qualify for a larger budget view;
unused budget is not filled with estimated results. Missing observations mean no
verified candidate within that budget, not a score of zero.

The result contract records observations at $10, $20, $50 and $100, plus the best
achieved result. The UI may expose a subset of those views. Changing a view never
starts inference. Total run spending is separate from credits at the best score.

## How credits are counted

Model credits use the reference pricing schedule recorded for that evaluation.
The schedule covers input, output (including reasoning), cache usage and any
supported long-context rates. Historical runs retain their original schedule.
See [model pricing](generic-harnesses.md#reference-prices-for-declared-models).

All declared models and harness workers share the run's budget. Usage includes
failed experiments, retries that consumed tokens, and calls after the best
candidate was found. Cache categories and reasoning are counted once. Builds,
verification compute and infrastructure are separate from research-model credits.

Credits are a comparison measure, not necessarily the provider's cash charge or
remaining subscription allowance. Funded OpenRouter settlement uses reported
provider charges; see [funding and allowances](platform-funded-inference.md).
Unknown usage or unsupported pricing cannot establish a verified score.

## Concurrent calls and budget limits

The gateway reserves credits before forwarding a request. A request with a large
history or output limit may be rejected while credits remain. Reduce its size
rather than repeating it unchanged; see [reservation errors](generic-harnesses.md#parallel-accounting-and-evaluation).

An already admitted response can finish above the cap. Current policy accepts
such overshoot only when the recorded admission evidence establishes that all
charged calls started before settled spending exhausted the cap. Older results
retain their original stricter policy. Costs are never reduced to fit a budget
view: a candidate recorded above $20 cannot qualify for the $20 comparison.

## Verified history and final verification

The history includes successful candidate evaluations, ties and regressions.
Calls still in flight when a candidate is evaluated count when their usage
settles, so a score may be recorded at a later, higher cumulative cost.

Final verification checks the saved terminal candidate independently. Its point
is recorded at full run cost, even if it repeats an earlier score. An earlier
verified candidate can remain the best point on the curve. Do not interpret final
verification as an additional improvement or subtract its preceding model usage.

## Yukon results

Yukon receives two minimizing values: best verified performance and cumulative
model credits at that result. The full curve, selected models, spending cap and
total usage remain available separately. A valid best result does not require
observations at every budget; an invalid run has no score tuple.

Publishing a receipt retrieves the existing verified result without another
research run. Existing receipts and published results retain their original
problem and pricing identities. See [publication](solver-guide.md#6-publish-to-yukon)
and [submission rules](cheat-filter.md).
