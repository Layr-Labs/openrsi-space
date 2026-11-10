# Troubleshooting

**Preserve the original source, local run, saved request, receipt and state
folder before retrying.** Use the same evaluator and Yukon account. Reconnecting
to an existing evaluation does not start research again; a new run can spend again.

## Check the existing run first

```sh
openrsi-space remote status EVALUATION_ID
openrsi-space remote diagnostics EVALUATION_ID --output diagnostics.json
openrsi-space remote logs EVALUATION_ID --output run-logs.zip
```

These retrieve status or owner-only diagnostics, not fresh inference. Logs may be
missing or truncated; inspect capture coverage. Keep downloaded files private.
If you selected `--state PATH`, keep using it. The evaluation ID alone does not
reconstruct missing local state.

## Find the failed stage

The [state model](submission-states.md) distinguishes execution,
verification, source availability and optional Yukon publication.

| What you see | What to do |
| --- | --- |
| Asked for an OpenRouter key during a subscription local test | Check the local provider: use `openai-chatgpt` or `claude-subscription` and its [login recipe](local-evaluation.md#3-prepare-only-the-selected-local-access-route), not local `openrouter`. |
| Local run failed or reports only wrapper completion | Inspect agent outcome, candidate verification and evidence completeness separately. Wrapper success alone is insufficient. |
| HTTP 400, no evaluation ID | Read the admission code and failing field. Keep the saved request. Do not assume a worker started; ask the operator if creation is unclear. |
| Submission response lost | Recover the unchanged saved request and original identity; do not invent a new request or silently resubmit altered source. |
| `queued` or `building` | Follow the existing evaluation; do not submit another just because it is waiting. |
| `running` or `verifying`, terminal disconnected | Reconnect with `remote wait EVALUATION_ID`. |
| Cancellation requested | Check status until it is terminal; in-flight requests can still be charged. |
| `failed` or `cancelled` | Inspect retained candidates, accounting and verification. Terminal runs cannot generally resume research. |
| `completed`, valid result unclear | Retrieve the verification result and receipt with `remote wait`; status alone is not validity. |
| Source missing from catalog | Inspect source publication separately; a verified result and source availability are different outcomes. |
| Verified result, missing Yukon submission | Retry optional publication with the existing receipt; no research rerun is needed. |

Use the specific error and recovery cases below.

## Ask for help safely

Start with the request/evaluation ID, time, safe error code, failed stage and what
you already tried. Report whether you think it is a harness or platform issue and
why. Do not paste keys, login files, private prompts or full traces. Keep even
sanitized logs private unless the user explicitly authorizes sharing them.

## Submission failed before I received an evaluation ID

Identify which operation failed. No evaluation ID alone does not prove that no
run exists. The CLI explicitly reports when a preparation failure happened before
an evaluation was submitted; a timeout after submission remains ambiguous.

| Symptom | Next action | Expected result / escalation |
| --- | --- | --- |
| `Local Dungeness check required` | Locate the original local record and use `--local-run PATH`. Compare source, problem, model/reasoning, recorded cap and complete settled exchanges using the [local evidence rules](platform-funded-inference.md#local-access-and-remote-eligibility). | Reuse a qualifying record. Start another paid local test only if the actual mismatch or missing evidence requires it. A valid local circuit is not required. |
| Local build, model access or runtime failed | Inspect `run.json` and the paths in its summary using [local outcomes and diagnostics](local-evaluation.md#local-outcomes-and-diagnostics). | Fix the identified local issue. An ended failed run may still qualify as evidence; its exit code alone does not decide eligibility. |
| Evidence upload failed | Read the printed diagnostic path, which may be `<state>/remote/diagnostics/upload-UUID.json` with no request ID. Resolve the reported size, privacy or service error before retrying. | This upload does not create an evaluation. Keep the original local records; a transient upload failure does not require another local research run. |
| HTTP 401 / missing login | Restore the same owner's Yukon login or key using [authentication handoff](solver-guide.md#yukon-authentication-when-needed), then retry the same retrieval or pending operation. | The client already attempts session renewal for Yukon keys. Persistent failure needs operator help; a personal model key does not replace Yukon authentication. |
| HTTP 403 | Check the owner account, evaluator and intended board against [endpoint selection](solver-guide.md), then inspect the error code. | If access or policy remains denied, contact the operator with the IDs. A bare 403 does not identify which policy failed. |
| TLS/certificate failure or refused redirect | Verify the configured endpoint. Use the [HTTPS troubleshooting guidance](maintainers/remote-api.md#authentication-and-model-access) to repair certificate/trust configuration. | Retry against the original trusted deployment after correction. Do not disable certificate validation or change deployment to recover an existing run. |
| HTTP 429 | Inspect `code`, `limit`, `current`, and `retry_after_seconds` when present. For an existing evaluation, monitor that ID; for a rejected submission, wait the indicated interval and retry its saved request. | Account concurrency, global capacity, submission rate and quota are different limits. For allowance or unresolved holds, use the funding section below. |
| HTTP 5xx, timeout, or connection lost during submit | Preserve state and follow [uncertain submission recovery](submission-recovery.md). | Retrieve the same evaluation or recover the same request. If recovery keeps failing, escalate with the request/correlation ID rather than changing the payload. |

Preparation errors may have neither a request ID nor an evaluation ID. Use the
failure time and available error/correlation fields in the support template.
An HTTP status alone is not enough to classify a source rejection or decide to rerun.

## I received HTTP 400 without an evaluation ID. Was anything run?

A rejection at admission is **before** the evaluation state machine, not a
terminal `failed` evaluation. See [admission and evaluation states](submission-states.md#current-admission-and-remote-evaluation).

A confirmed admission rejection before job creation has no evaluation to resume.
A timeout or missing response alone does not establish that the request was rejected.
The CLI retains sanitized HTTP diagnostics in:

```text
<state>/remote/diagnostics/<request-id>.json
```

Inspect the error code, stage, field, expected value, and correlation/edge IDs.
After an operator fixes a platform rejection, retry the unchanged saved request.
If the actual source or settings need correction, follow the matching-evidence
rules; do not edit the saved request or recorded local evidence to make it match.

| Error or symptom | Next action |
| --- | --- |
| `source_not_publishable` / `local_evidence_not_private` | Give the operator the request ID and ask them to inspect retained diagnostics for the finding's file or event, rule, and location. A generic error does not establish that a real credential exists. Do not alter placeholders or regenerate evidence based on a guess. Do not send the matching secret or your source/evidence archive to support. Remove a confirmed real credential before submitting again. |
| `local_evidence_budget_cap_missing` | Update the submission client and re-export from the original local run using `--local-run PATH`. A new local run is unnecessary if that record already contains a sufficient cap. |
| `local_evidence_budget_cap_insufficient` | Lower the requested remote cap or select a qualifying local run with a sufficient recorded cap. Actual spending may be below the cap; there is no minimum-spend percentage. |
| `local_evidence_mismatch` | Compare source, problem, exact model or supported provider equivalent, and reasoning settings. Use matching original evidence; do not relabel it. |
| `release_configuration_mismatch`, screening unavailable, or builder unavailable | Keep the request and evidence. Ask the operator to repair the service before retrying. Do not install a different problem release or supply a personal model key as a workaround. |
| Account allowance or funding unavailable | Inspect `remote funding` and `remote funding-policy`. Reservations and unsettled charges can affect availability. A new Yukon key does not create a new account allowance. |

For size errors, use `remote limits ./my-harness` and the reported limit;
see [source limits](source-limits.md) and [local evidence requirements](platform-funded-inference.md).

## Which failure can I fix myself?

Read `openrsi-space remote diagnostics EVALUATION_ID`. Available diagnostic
sections include `worker`, `runtime`, `verification`, `evaluations.events`, and
`model_failures.events`. Use their codes and recorded source locations to choose
the next step. Several failures can coexist; the latest event is not necessarily
the root cause. Missing information is unknown, not a successful check.

| Code or symptom | Who acts and what to do | What happens to this attempt? |
| --- | --- | --- |
| `HARNESS_EXIT_NONZERO` or a harness-reported exception | Solver: inspect the recorded exception/location and private harness logs, reproduce locally, and fix the general-purpose harness. | A retained candidate may still verify. Check the final result before choosing another run. Changed source requires matching local evidence for a new submission. |
| `CANDIDATE_REJECTED` | Solver: inspect trusted evaluator feedback and use the assigned evaluator during local development. | The candidate failed a check. While the run is active, the harness may try others; final `valid: false` means no eligible score. A rejected candidate is not by itself an infrastructure failure. |
| `HARNESS_TIMEOUT` or `EVALUATION_LIMIT_REACHED` | Solver: inspect configured limits and retained candidate results. | A limit was reached; it does not establish that all research failed. Review results before authorizing further work. |
| `WORKER_FAILED`, `RUNTIME_ERROR`, `EVALUATOR_ERROR`, `EVALUATOR_RESULT_UNREADABLE`, `EVALUATION_TIMEOUT` | Operator investigates the retained report; solver provides the ID and whether local checks reproduce the failure. | The code alone does not establish the cause. Ask whether existing results can be recovered before starting another run. |
| `MODEL_ACCESS_UNAVAILABLE` | Operator: investigate hosted model access. Solver should not send a personal model key to repair a platform-funded run. | This attempt ended. Fixing access does not resume it. |
| `MODEL_USAGE_UNAVAILABLE` / interrupted stream with missing usage | Operator: investigate the specific request's usage and settlement. Solver can separately review harness error handling. | Incomplete accounting blocks a verified receipt even if a candidate passed. A later successful model call does not settle the missing request. |
| `MODEL_RESERVATION_EXCEEDS_REMAINING_BUDGET` | Solver: inspect required/available amounts and reduce context or the harness's explicit output-token limit for future calls. | The rejected request was not sent upstream when diagnostics say `upstream_request_sent: false`. Do not infer a charge or increase the budget just to diagnose it. |
| Unknown code, absent report, or result binding/validation error | Preserve the ID and state; ask the operator to inspect the retained records or deployment compatibility. | There is insufficient evidence to decide whether another research run is needed. |

For failure details and limits of retained diagnostics, see
[troubleshooting an owned run](maintainers/remote-api.md).

## How do I start a new attempt after a terminal result?

Use this only when you intend another research run. To retrieve a result or
finish publication, use the existing evaluation ID instead.

1. Confirm the old evaluation is terminal with `remote status EVALUATION_ID`.
   Resolve any remaining candidate/receipt recovery or funding investigation first.
2. Run `remote wait EVALUATION_ID` to process the terminal result. For `failed`
   or `cancelled`, its nonzero exit is expected. For `completed`, inspect `valid`
   and preserve the receipt. Previously authorized automatic publication can also
   continue here. If result validation or local file writing fails, resolve that
   error before proceeding; do not delete pending records manually.
3. Check `remote funding` for settlement and available allowance. Confirm the
   cause of failure is addressed and your source/settings still have qualifying
   local evidence. An infrastructure failure alone does not require another local run.
4. With authorization for the new spending cap, run your reviewed `remote submit`
   command with its source, settings and matching `--local-run PATH`. Record the
   new request ID and evaluation ID. This starts fresh research and can incur charges.

The current CLI keeps an unchanged submission's pending request after `status`,
even when the result is terminal. `wait` clears it after processing a terminal
failure/cancellation or validating a completed result; a terminal `cancel` response
also clears it when local session state is available. Therefore **the same submit
command can recover the old evaluation before cleanup and create a new evaluation
after cleanup**. If it returns the old ID, inspect/process that attempt rather
than changing source or deleting state to force a restart.

## A candidate passed, but final verification or saving failed. Did I lose it?

Read the [separate execution and verification outcomes](submission-states.md#current-separate-outcomes).
An execution failure can coexist with a passed verification of a retained circuit;
if you have a valid receipt, follow publication recovery rather than restarting research.
Here, harness execution failure is distinct from the overall evaluation lifecycle
status `failed`: the current client only exports a receipt through `wait` when
the overall status is `completed` and result validation succeeds. If the overall
status is `failed` or `cancelled` and you have no valid receipt, ask the operator
about retained candidate recovery; ordinary `wait` cannot turn it into a scored result.

An intermediate valid candidate, final verification, and a published result are
different outcomes. Keep the evaluation ID and diagnostics. Retained candidate
artifacts may allow operator recovery, but a score in stdout is not a verified
receipt, and verification-only retry is not a general solver command today.
Ask whether the existing result can be recovered **before authorizing another
research run**. Do not edit a receipt or manually insert a score.

If `wait` reports `Submission changed during evaluation`, the validated receipt
may already be saved at `<state>/remote/evaluations/EVALUATION_ID/verification.json`,
with its judgment in `judgment.json`. The export to the changed harness directory
was refused. Inspect the retained judgment's `valid` field and use that original
receipt with the [manual publication workflow](submission-recovery.md), or
opt into [automatic publication on the existing ID](artifact-sharing.md#stopping-the-command-and-recovering).
Do not rerun research or edit receipt bindings to match the changed directory.

For local testing, a failed or cancelled ended run can still qualify as evidence
when its model exchanges and settled accounting are complete and the remaining
checks pass. Conversely, wrapper exit code zero does not prove that the agent
succeeded. See [local outcomes and diagnostics](local-evaluation.md#local-outcomes-and-diagnostics).

## Why is my harness source not public?

Source publication and leaderboard publication are separate. Inspect the evaluated
source outcome at `outcomes.publication.source`, then its sharing and artifact availability:

```bash
openrsi-space remote diagnostics EVALUATION_ID
openrsi-space remote sharing EVALUATION_ID
openrsi-space remote artifacts EVALUATION_ID
```

| Reported source outcome | Next action |
| --- | --- |
| `pending` while the run is active | Wait for it to stop and for publication screening. Source is not expected to be public during execution. |
| `pending` after the run ends, or `retryable_failure` | Preserve the ID and reported error; ask the operator to inspect publication processing. These commands inspect availability; they do not retry source publication. |
| `blocked` | Ask the operator for the retained screening finding's rule/location. Do not assume the finding proves a real secret, or attempt to bypass screening. Changes to your local directory cannot change the evaluated source archive. |
| `published`, but source is missing from the UI | Compare the evaluation ID/source hash in the artifact manifest with the intended Yukon result. Give the operator the IDs if the manifest and UI disagree. Do not start a research run to repair a display problem. |
| Outcome absent or endpoint unavailable | Treat availability as unknown; request operator investigation rather than assuming publication succeeded. |

The `remote publish --harness --confirm-source-reviewed` workflow in
[artifact sharing](artifact-sharing.md#download-harness-source-or-publish-historical-source)
publishes reviewed historical source. It is not a general bypass for a blocked new
submission and does not publish a score to Yukon. It releases the original evaluated
bytes, so review that archive before using it.

## Publication recovery

Use the [publication state table and retry commands](artifact-sharing.md#stopping-the-command-and-recovering). Do not restart research to fix a Yukon job or source-display problem.
