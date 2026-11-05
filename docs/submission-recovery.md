# Submission recovery guide

Use this guide when a local check, submission, remote run or publication fails.
Start with the checklist and choose the symptom that matches what you can see.
Keep the original state and identifiers: recovering an existing operation and
starting another research run have different effects on spending.

The [state reference](submission-states.md#current-admission-and-remote-evaluation) explains the
lifecycle; [architecture](architecture.md) explains component responsibilities.

## What should I do first?

1. Keep the original harness, local run, receipt, and OpenRSI state directory.
   Keep using the same evaluator endpoint and Yukon account.
2. If you have an evaluation ID, inspect the existing run:

   ```bash
   openrsi-space remote status EVALUATION_ID
   openrsi-space remote diagnostics EVALUATION_ID --output diagnostics.json
   ```

   These commands do not start inference. Use `status` to identify the lifecycle
   state and `diagnostics` to identify the failure category. If harness output is
   needed, download it with `openrsi-space remote logs EVALUATION_ID --output run-logs.zip`.
   Logs may be incomplete or unavailable; inspect the reported capture coverage.
   Files are saved locally. Keep them private even after sanitization.
3. If you have no evaluation ID, use the no-ID rows below. A local preparation
   failure, an admission rejection and a lost submission response need different
   recovery actions.
4. Match the observed symptom to the table. Do not delete pending-request files,
   invent a new request ID, or change source to bypass an uncertain outcome.

Use the [current submission client](solver-guide.md#use-the-current-submission-client-with-a-pinned-yukon-board).
The examples assume it is installed as `openrsi-space`. In a Yukon-pinned checkout,
`uv run` can select an older client instead. If you originally selected a state
directory explicitly, retain it: `openrsi-space --state /path/to/state remote status EVALUATION_ID`.

## Which recovery path matches my submission's state?

Choose the symptom you can observe. Retrying a request, reconnecting to a run
and restarting research are different actions; see the [state model](submission-states.md) for their semantics.

| What you observe | What to do next | Can this start another paid run? |
| --- | --- | --- |
| Confirmed admission rejection, no evaluation ID | [Read the admission error](#i-received-http-400-without-an-evaluation-id-was-anything-run); preserve the original request. | Correcting and resubmitting can create the first run once accepted. |
| Local check or evidence upload failed, no evaluation ID | [Identify the failed preparation step](#submission-failed-before-i-received-an-evaluation-id). | Inspection does not; a new local test or accepted submission can. |
| Login, TLS, HTTP 403/429 or service error | [Resolve the access or transport error](#submission-failed-before-i-received-an-evaluation-id), preserving any existing operation. | Retrying a submit can create the intended run if it was not already accepted. |
| Response lost, outcome unknown | [Recover the unchanged saved request](#can-i-resume-after-closing-my-terminal-or-losing-the-connection). | It may create the intended run if the original never arrived; it should not duplicate an existing evaluation. |
| `queued` or `building`, waiting for capacity | [Wait on the existing evaluation](#the-run-is-waiting-for-infrastructure-should-i-submit-again). | No new run; the accepted run may proceed and incur usage. |
| `running` or `verifying`, connection lost | [Reconnect with `remote wait`](#can-i-resume-after-closing-my-terminal-or-losing-the-connection). | No new run; ongoing work may still incur usage. |
| Progress stopped changing | [Check phase and metric freshness](#the-run-is-waiting-for-infrastructure-should-i-submit-again). | Inspection does not; the active run may still incur usage. |
| Cancellation requested, run still active | [Confirm cancellation separately](#how-do-i-cancel-and-confirm-the-run-stopped). | No new run; in-flight work may still incur charges. |
| `failed` or `cancelled` | [Classify the failure](#which-failure-can-i-fix-myself), then [inspect retained results](#a-candidate-passed-but-final-verification-or-saving-failed-did-i-lose-it). | A fresh research attempt can incur new charges. Status retrieval cannot restart this one. |
| `completed`, validity unclear | [Retrieve the final validity result](#how-do-i-tell-whether-my-result-is-verified). | No research inference; previously authorized publication may continue. |
| Verification rejected or failed | [Identify candidate, evaluator or accounting failure](#which-failure-can-i-fix-myself). | Diagnosis does not; a new research attempt can. |
| Allowance remains reserved, or run stopped below its cap | [Inspect funding and accounting](#why-is-my-allowance-still-reserved-or-my-run-stopped-below-budget). | Inspection does not. |
| Harness source is missing, blocked or not yet public | [Inspect source publication](#why-is-my-harness-source-not-public). | Inspection does not. |
| Verification passed, Yukon publication missing or failed | [Recover publication using the existing receipt](#verification-succeeded-but-yukon-publication-failed-must-i-rerun-research). | No model inference is needed for publication. |
| Old attempt is terminal and you intend to run again | [Start a new attempt deliberately](#how-do-i-start-a-new-attempt-after-a-terminal-result). | Yes; this is a separate research run. |
| `Unknown local evaluation` | [Locate the original client state](#which-id-do-i-need). | Inspection does not. |

Use the [state reference](submission-states.md#current-separate-outcomes) when
execution, verification and publication report different outcomes. In particular,
`completed` is not synonymous with a valid circuit, and `receipt_delivered` is not
confirmation that a score is on the Yukon board.

## Publish a verified receipt

1. Retrieve the complete service-issued `verification.json` after verification.
2. Copy it unchanged to `submission/verification.json` in the intended Yukon
   benchmark checkout, using the same account that owns the evaluation.
3. Run `yukon run` to check the receipt, then `openrsi-space yukon-submit` with
   the methodology note, harness/model attribution and dependencies.
4. Inspect the Yukon submission/job to confirm acceptance on the intended board.

See the [solver guide](solver-guide.md#6-publish-to-yukon) for commands and
[endpoint selection](verifier-endpoint.md) for board/environment matching.
The hosted workflow authenticates separately and retrieves the retained result;
it does not need your model key or start another research run. A receipt or a
score in a submission note does not by itself authorize publication.
Keep the original receipt, note and IDs until publication is confirmed. Do not
edit source, problem, policy, owner or score fields in a receipt. Historical
receipts retain their recorded problem and scoring policy.

## How do I tell whether my result is verified?

`remote status` reports the lifecycle `status`, available `reason`/`error`,
`progress`, `diagnostics`, and any saved client publication summary. The current
CLI does **not** print the result's top-level `valid` field in this command.
Use its diagnostic outcomes to distinguish the following cases before retrieving
the validated result:

| Question | Field in `remote diagnostics` output | Field in `remote status` output |
| --- | --- | --- |
| Did the harness execute successfully? | `outcomes.execution` | `diagnostics.outcomes.execution` |
| Did final verification pass? | `outcomes.verification` | `diagnostics.outcomes.verification` |
| Is harness source published? | `outcomes.publication.source` | `diagnostics.outcomes.publication.source` |
| Did the verifier deliver a receipt? | `outcomes.publication.leaderboard` | `diagnostics.outcomes.publication.leaderboard` |

`passed` is the verification outcome; `receipt_delivered` alone is not Yukon
acceptance. Neither `receipt_available: true` nor an exit code of zero from
`remote status` establishes a valid score. Older reports may omit outcomes;
missing fields mean unknown. Diagnostic reports themselves are not score evidence.

To retrieve and validate the final result, run:

```bash
openrsi-space remote wait EVALUATION_ID
```

If the run is active, this waits for it. If it is terminal, this processes its
retained result. It never starts another research run. If automatic publication
was previously selected, it also continues that publication with your local login.

| What `wait` reports | Meaning and next step |
| --- | --- |
| `status: completed`, `valid: true`, with `verification` and `judgment` paths | The client validated the retained result. Preserve the receipt at the printed `verification` path. Inspect `publication.state` separately. |
| `status: completed`, `valid: false`, `publication.state: not_eligible` | No eligible verified score. Read `reason` and the reported `next_command` for diagnostics; use the failure table below. |
| `Remote evaluation failed` or `cancelled` | This attempt is terminal. A nonzero exit is expected. Inspect diagnostics and retained results before considering another attempt. |
| Result binding, accounting validation or receipt-write error | Retrieval did not finish successfully. Preserve the evaluation ID and state; resolve the reported local file issue or ask the operator about the retained result. Do not substitute a score or resubmit research to recover a receipt. |

An illustrative successful result, with other fields omitted:

```json
{
  "status": "completed",
  "valid": true,
  "verification": "/path/to/my-harness/verification.json",
  "publication": {"state": "not_requested"}
}
```

This result is verified but not published to Yukon. `not_requested` includes a
publication `next_command` in the full output. Follow it with your intended board
and public metadata, or use the [manual receipt workflow](#publish-a-verified-receipt).
The mere existence of a file named `verification.json` does not establish validity.

## Which ID do I need?

Use the [identifier reference](submission-states.md#identifiers-and-operation-identity)
to distinguish request, evaluation, evidence and Yukon IDs.

The CLI also needs its saved session for `remote status` and `remote wait`.
An ID alone does not reconstruct lost local client state. If it says “Unknown
local evaluation,” first locate the original working directory and `--state`
directory. New state normally lives in `.openrsi/`; older `.catalyst/` state
remains supported. If the session cannot be recovered, give the evaluation ID
to the operator rather than submitting a replacement blindly. With the correct
endpoint and owner login, `remote diagnostics` and `remote logs` can still use
the evaluation ID without that saved session.

## Can I resume after closing my terminal or losing the connection?

You can reconnect to `queued`, `building`, `running` or `verifying` work without
creating a new evaluation:

```bash
openrsi-space remote wait EVALUATION_ID
```

Stopping `remote wait` does not cancel the remote run. Reconnecting waits for
the same evaluation and saves its verified result when complete. If the run
already completed, this retrieves its result without another research run.
Use `remote cancel EVALUATION_ID` only when you intend to stop execution.

If the original submission response was lost and you have no evaluation ID,
first check earlier CLI output and `<state>/remote/evaluations/` for a saved
evaluation. If one exists, use its ID with `remote status` or `remote wait`.
Otherwise, with the original pending request still saved, retry the **original
submit command with unchanged inputs and the same state**. The CLI reuses the
saved request ID. It may create the intended run if the first request never arrived.

This is recovery of a pending submission, not a general rule for repeating
`submit`. After `wait` processes a terminal result, the CLI clears the pending
request and the same submit command can start a new run. If the original state
is lost or no saved operation can be identified, contact the operator before
submitting again. See [starting a new attempt](#how-do-i-start-a-new-attempt-after-a-terminal-result).

## Submission failed before I received an evaluation ID

Identify which operation failed. No evaluation ID alone does not prove that no
run exists. The CLI explicitly reports when a preparation failure happened before
an evaluation was submitted; a timeout after submission remains ambiguous.

| Symptom | Next action | Expected result / escalation |
| --- | --- | --- |
| `Local Dungeness check required` | Locate the original local record and use `--local-run PATH`. Compare source, problem, model/reasoning, recorded cap and complete settled exchanges using the [local evidence rules](platform-funded-inference.md#local-access-and-remote-eligibility). | Reuse a qualifying record. Start another paid local test only if the actual mismatch or missing evidence requires it. A valid local circuit is not required. |
| Local build, model access or runtime failed | Inspect `run.json` and the paths in its summary using [local outcomes and diagnostics](local-evaluation.md#local-outcomes-and-diagnostics). | Fix the identified local issue. An ended failed run may still qualify as evidence; its exit code alone does not decide eligibility. |
| Evidence upload failed | Read the printed diagnostic path, which may be `<state>/remote/diagnostics/upload-UUID.json` with no request ID. Resolve the reported size, privacy or service error before retrying. | This upload does not create an evaluation. Keep the original local records; a transient upload failure does not require another local research run. |
| HTTP 401 / missing login | Restore the same owner's Yukon login or key using [model access](live-models.md#first-time-login), then retry the same retrieval or pending operation. | The client already attempts session renewal for Yukon keys. Persistent failure needs operator help; a personal model key does not replace Yukon authentication. |
| HTTP 403 | Check the owner account, evaluator and intended board against [endpoint selection](verifier-endpoint.md), then inspect the error code. | If access or policy remains denied, contact the operator with the IDs. A bare 403 does not identify which policy failed. |
| TLS/certificate failure or refused redirect | Verify the configured endpoint. Use the [HTTPS troubleshooting guidance](remote-evaluation.md#authentication-and-model-access) to repair certificate/trust configuration. | Retry against the original trusted deployment after correction. Do not disable certificate validation or change deployment to recover an existing run. |
| HTTP 429 | Inspect `code`, `limit`, `current`, and `retry_after_seconds` when present. For an existing evaluation, monitor that ID; for a rejected submission, wait the indicated interval and retry its saved request. | Account concurrency, global capacity, submission rate and quota are different limits. For allowance or unresolved holds, use the funding section below. |
| HTTP 5xx, timeout, or connection lost during submit | Preserve state and follow [uncertain submission recovery](#can-i-resume-after-closing-my-terminal-or-losing-the-connection). | Retrieve the same evaluation or recover the same request. If recovery keeps failing, escalate with the request/correlation ID rather than changing the payload. |

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

## The run is waiting for infrastructure. Should I submit again?

No. Inspect the existing evaluation. “Waiting for infrastructure capacity” means
the accepted attempt is waiting for the service to become available. Use:

```bash
openrsi-space remote status EVALUATION_ID
openrsi-space remote wait EVALUATION_ID
```

When available, `progress.phase` identifies review, build, startup, research or
verification; `progress.phase_elapsed_seconds` measures that phase, and
`progress.snapshot_age_seconds` measures the age of the metrics. A rising metric age means
stale observations, not proof that research stopped. Fresh metrics with unchanged
request counts can mean a long model request or evaluation. Missing usage is not
zero usage. `wait` reports phase changes and periodic progress without creating a run.

This guide does not specify a queue or verification completion deadline. If repeated
status checks show increasing metric age or no phase progress beyond an operator's
communicated expectation, contact the operator with the evaluation ID and times
of your observations. If no expectation was provided, ask whether the current phase
is healthy. Keep monitoring the same ID or cancel if you no longer want the run.

## How do I cancel and confirm the run stopped?

```bash
openrsi-space remote cancel EVALUATION_ID
openrsi-space remote status EVALUATION_ID
```

`cancellation_requested: true` acknowledges a request, not completed shutdown.
Monitor the same ID until its lifecycle status is terminal: `cancelled`, `failed`
or `completed` (completion may race with cancellation). Then inspect diagnostics,
retained results and `openrsi-space remote funding`. Incurred charges still count;
terminal execution does not by itself prove funding settlement.

If cancellation remains pending across repeated checks, give the operator the ID
and request time. Do not create a replacement while the original is still active.
Closing `remote wait` only stops monitoring; it is not cancellation.

## The remote run stopped unexpectedly. Can it continue where it stopped?

First distinguish a disconnected client from a terminal `failed` or `cancelled`
evaluation. If the evaluation is still active, use `remote wait` for the same ID.

There is currently **no general remote checkpoint-resume command**. Interrupted
started work is marked failed rather than silently replaying potentially paid
calls. A checkpoint saved by your harness does not by itself make the remote run
resumable.

After a terminal build/startup failure is repaired, a fresh remote attempt may
be needed. Reusing the old request ID retrieves that old attempt, not a restart.
Confirm the old attempt's terminal status and funding settlement before starting
another authorized attempt. A failure after inference began does not erase its
incurred usage; do not assume every failed run cost zero.

An unchanged, qualifying local evidence bundle can still be reused for a new
attempt, subject to its bindings, cap, expiry, and current admission checks.
A new local run is not automatically required just because remote infrastructure failed.

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
[troubleshooting an owned run](remote-evaluation.md#troubleshooting-an-owned-run).

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

## Why is my allowance still reserved, or my run stopped below budget?

```bash
openrsi-space remote funding
openrsi-space remote funding-policy
openrsi-space remote diagnostics EVALUATION_ID
```

The first two commands inspect account allowance and current policy. Use diagnostics
for a particular run. None starts inference.

| Observation | Next action and expected result |
| --- | --- |
| Active run holds its requested cap | Monitor or cancel that evaluation. Its reservation reduces available allowance while work is outstanding. |
| Run ended, but allowance has not returned | Recheck `remote funding` and the run's accounting diagnostics. If usage is incomplete or a hold persists, ask the operator to reconcile the retained run/request. Unresolved holds do not expire automatically; waiting until midnight or getting another key does not clear them. Do not assume a terminal run cost zero. |
| Settled usage exhausted the rolling allowance | Inspect `allowance` and the reported next settled-charge expiry. Wait for allowance or use a lower cap within both policy and local-evidence limits for a separately authorized new run. |
| A model request was refused with budget remaining | Inspect the reservation error's required and available amounts. A long context or large output-token limit can require more than the remainder. Shorten context or lower the explicit output limit; the cap is a maximum, not guaranteed spend. |

Live usage and missing/incomplete billing are not final charges. See
[funding and settlement](platform-funded-inference.md#local-access-and-remote-eligibility)
for policy details, units and the difference between provider charges and normalized credits.

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
receipt with the [manual publication workflow](#publish-a-verified-receipt), or
opt into [automatic publication on the existing ID](automatic-publication.md#stopping-the-command-and-recovering).
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

## Verification succeeded, but Yukon publication failed. Must I rerun research?

No. Preserve the receipt. Publication recovery uses the retained verified result
without another research run.
OpenRSI currently reports leaderboard delivery as `not_confirmed` or
`receipt_delivered`; neither proves that Yukon's publication job succeeded.
Check the Yukon submission/job separately. Source publication also does not prove
leaderboard publication. See [publication outcomes](submission-states.md#current-separate-outcomes).

First read the saved client publication record:

```bash
openrsi-space remote publication EVALUATION_ID
```

This is a local status read; it does not upload or refresh Yukon's job status.
Keep the original state directory, endpoint and owner login. The client states
below describe a different layer from the server's receipt-delivery outcomes above.

| Client state (`state` here; `publication.state` in `wait` output) | Next action and expected result |
| --- | --- |
| `not_requested` | Choose automatic publication on the existing ID using the [documented `wait --publish-to-yukon` command](automatic-publication.md#stopping-the-command-and-recovering), or use the manual receipt workflow. No research rerun is needed. |
| `pending` | Run `remote wait EVALUATION_ID` to finish verification and continue previously authorized publication. |
| `submitting` or `awaiting_yukon` | Run `remote publication EVALUATION_ID --retry` to recover the same submission or refresh its outcome. Keep the saved archive and idempotency key; this recovers the existing publication operation. |
| `needs_authentication` | Restore the same owner's local Yukon login, then run `remote publication EVALUATION_ID --retry`. |
| `retryable_failure` | Read `error_code` and the recovery message. Resolve the issue, then retry publication only. If the code is `yukon_publication_failed`, ask the operator to repair the existing Yukon job first; retry cannot override its failure/rejection. |
| `not_eligible` | Inspect the evaluation's final validity and diagnostics. This attempt has no eligible result for automatic publication. |
| `published` | Yukon has reported acceptance. Retain the submission/job IDs; if the intended board does not show the result, ask the operator to investigate those IDs. |

Publication polling waits up to five minutes per invocation. Remaining in
`awaiting_yukon` is a reason to reconnect using the output's command, not to resubmit
research. If a missing job ID cannot be recovered, give the operator the available
IDs. See [automatic publication recovery](automatic-publication.md#stopping-the-command-and-recovering).

For manual publication, inspect `yukon submissions --all --json` from the intended
board checkout and locate the matching submission/job. Publication and Git branch
errors do not invalidate an otherwise verified research result.

If Yukon created a job but OpenRSI's execution binding did not finish, run this
from the original receipt checkout, using the same owner account and endpoint:

```bash
openrsi-space yukon-bind --job-id YUKON_JOB_ID --benchmark-id BENCHMARK_ID
```

This repairs only the binding; it does not retry a failed GitHub publication job.
The `yukon-submit` helper also retains a pending binding for retry. If submission
outcome is unknown, inspect `yukon submissions` or ask the operator before
uploading again. Do not delete the helper's pending record to bypass its duplicate
guard. See [Yukon publication](remote-evaluation.md#receipts-and-yukon).

## How do I ask for help without sharing private data?

Use the private support channel supplied with your OpenRSI access. This repository
does not name a universal support address. If you were not given a channel, ask
the person or team that provided your access to connect you with the evaluator
operator; do not post private diagnostics in a public issue to find support.

When contacting the operator privately, start with only these identifiers and
error details. The operator should inspect the records already held by the
service first; you do not need to attach source, evidence, logs, or transcripts.

```text
Request ID / evaluation ID (whichever exists):
Yukon submission/job ID (if publication failed):
Approximate time of failure (UTC):
HTTP status and error code, if shown:
Correlation/edge ID, if no request or evaluation ID is available:
Observed lifecycle/publication state and time it last changed (if known):
Requested help: access / stuck run / cancellation / accounting / retained result / publication
```

Copy only those fields, not the full response or log contents. Do not post the
report in a public issue or submission note. Keep API keys, login files,
authorization headers, environment dumps, local filesystem paths, state
directories, source/evidence archives, and raw transcripts out of support messages.
Preserve your original files locally. Sanitization is not a guarantee that a
downloaded file is safe to share.

For coding agents: diagnose first, preserve identifiers and artifacts, distinguish
retrieval from a new paid attempt, and reuse existing user authorization only
within its stated scope. Permission to submit a run is not permission to send
additional files or private content to support. Do not upload or paste them on
the user's behalf without their explicit permission. Do not claim a run resumed
merely because status retrieval worked, or treat a service/review availability
failure as a cheating verdict.
