# Submission states and recovery

This is the reference for interpreting an OpenRSI submission's progress.
It describes implemented behavior. Start with the state and outcome tables below,
then use the [recovery checklist](#what-should-i-do-first) and
[symptom table](#which-recovery-path-matches-my-submissions-state).
For component boundaries, see [architecture](architecture.md).

## Current: admission and remote evaluation

Admission checks happen before an evaluation is created. A confirmed admission
rejection has a request ID but no evaluation ID. A lost HTTP response is different:
the evaluation may exist, so recover the original request rather than create another.

Once admitted, the evaluation has a persistent ID and follows this normal path:

```text
queued → building → running → verifying → completed
```

| State | Meaning |
| --- | --- |
| `queued` | Accepted and waiting to be claimed. |
| `building` | Preparing the run, including screening, building and startup. This does not establish that inference has begun. |
| `running` | Harness execution has started; inspect usage separately to see whether model calls occurred. |
| `verifying` | Processing and checking the run's result. |
| `completed` | Result processing finished. Inspect the verification outcome: completion alone does not mean a valid circuit. |
| `failed` | This attempt stopped with an error. Preserve its result and diagnostics. |
| `cancelled` | This attempt was cancelled. Charges already incurred still count. |
| `awaiting_credentials` | A supported credential-handoff path is waiting for model access and may return to `queued`. This is not a request to supply a personal provider key for a platform-funded run. |

Build, execution and verification can end in `failed` or `cancelled`.
Queued or credential-waiting evaluations can be cancelled before execution.
Cancellation of active work is a request; it is not necessarily instantaneous.
`completed`, `failed` and `cancelled` are terminal for that evaluation attempt.

Transitions are recorded durably and invalid transitions are rejected. Recovery
after a worker interruption marks started work failed (or cancelled if requested);
it does not automatically replay potentially paid calls.

## Current: separate outcomes

The evaluation state is only one part of the result. Keep these outcomes distinct:

| Dimension | Current outcomes | Interpretation |
| --- | --- | --- |
| Execution | `not_started`, `running`, `completed`, `failed`, `cancelled` | What happened to the harness execution. A retained circuit can sometimes verify even after the harness failed. |
| Verification | `not_started`, `running`, `passed`, `rejected`, `failed`, `cancelled` | Whether the result was checked and valid; a check failure is different from an invalid circuit. |
| Source publication | `pending`, `published`, `blocked`, `retryable_failure` | Availability of the harness source under the source-publication policy. |
| Leaderboard publication | `not_confirmed`, `receipt_delivered` | What OpenRSI currently knows about receipt delivery. Neither value confirms successful Yukon publication. Inspect the Yukon submission/job. |

These are reported outcomes, not four independently retryable execution engines.
In particular, source publication is separate from publishing a verified receipt
to the Yukon leaderboard. A published source archive does not imply a valid score.

## Current: identifiers and safe retries

| Operation | Record to preserve | Effect of recovery |
| --- | --- | --- |
| Admission | Original request ID and unchanged saved request | Recover the same evaluation if one was created; do not duplicate it. |
| Remote execution | Evaluation ID and original client state | Retrieve status or wait for the existing attempt. This does not resume a stopped process. |
| Verification | Retained result and verified receipt, when available | Preserve the result; there is no general solver-facing verification-only retry command today. |
| Yukon publication | Receipt, Yukon submission/job IDs and pending publication state | Recover publication or its execution binding without another research run. The correct action depends on which step failed. |

A terminal evaluation is not reopened by retrying its request ID. A fresh research
attempt is a separate, potentially paid operation. Conversely, a Yukon publication
failure must not require research to run again when a valid receipt is retained.
See the [publication recovery steps](#verification-succeeded-but-yukon-publication-failed-must-i-rerun-research).

Keep private state and downloaded diagnostics on your machine. For support, share
only the identifiers and sanitized error fields listed in the
[support instructions](#how-do-i-ask-for-help-without-sharing-private-data).

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

## What should I do first?

1. Keep the original harness, local run, receipt, and OpenRSI state directory.
   Keep using the same evaluator endpoint and Yukon account.
2. If you have an evaluation ID, inspect the existing run:

   ```bash
   openrsi-space remote status EVALUATION_ID
   openrsi-space remote diagnostics EVALUATION_ID --output diagnostics.json
   openrsi-space remote logs EVALUATION_ID --output run-logs.zip
   ```

   These commands do not start inference. Logs may be incomplete or unavailable;
   the diagnostic export reports capture coverage. The output files are saved on
   your machine, not uploaded to support. Treat downloaded logs as private even
   after sanitization; this guide does not ask you to share them.
3. Match the observed state to the recovery table below. Do not delete pending-request files, invent
   a new request ID, or change source just to bypass an error.

Use the [current submission client](solver-guide.md#use-the-current-submission-client-with-a-pinned-yukon-board).
The examples assume it is installed as `openrsi-space`. In a Yukon-pinned checkout,
`uv run` can select an older client instead. If you originally selected a state
directory explicitly, retain it: `openrsi-space --state /path/to/state remote status EVALUATION_ID`.

## Which recovery path matches my submission's state?

Use the state and outcome tables above to choose the recovery action. Retrying
a request, reconnecting to a run and restarting research are different actions.

| What you observe | What to do next | Can this start another paid run? |
| --- | --- | --- |
| Confirmed admission rejection, no evaluation ID | [Read the admission error](#i-received-http-400-without-an-evaluation-id-was-anything-run); preserve the original request. | Correcting and resubmitting can create the first run once accepted. |
| Response lost, outcome unknown | [Recover the unchanged saved request](#can-i-resume-after-closing-my-terminal-or-losing-the-connection). | It may create the intended run if the original never arrived; it should not duplicate an existing evaluation. |
| `queued` or `building`, waiting for capacity | [Wait on the existing evaluation](#the-run-is-waiting-for-infrastructure-should-i-submit-again). | No new run; the accepted run may proceed and incur usage. |
| `running` or `verifying` | [Reconnect with `remote wait`](#can-i-resume-after-closing-my-terminal-or-losing-the-connection). | No new run; ongoing work may still incur usage. |
| `awaiting_credentials` | Inspect the reported access issue. For platform-funded runs, ask the operator; do not supply a personal model key. | Do not submit a replacement. Resolving access can allow the existing run to start. |
| `failed` or `cancelled` | [Inspect the stopped attempt](#the-remote-run-stopped-unexpectedly-can-it-continue-where-it-stopped); check retained verification results before retrying research. | A fresh research attempt can incur new charges. Status retrieval cannot restart this one. |
| `completed`, verification not passed | [Distinguish final verification from candidate success](#a-candidate-passed-but-final-verification-or-saving-failed-did-i-lose-it). | Retrieval does not; a newly authorized research attempt can. |
| Verification passed, Yukon publication missing or failed | [Recover publication using the existing receipt](#verification-succeeded-but-yukon-publication-failed-must-i-rerun-research). | No model inference is needed for publication. |

Use the [state reference](submission-states.md#current-separate-outcomes) when
execution, verification and publication report different outcomes. In particular,
`completed` is not synonymous with a valid circuit, and `receipt_delivered` is not
confirmation that a score is on the Yukon board.

## Which ID do I need?

| Identifier | Purpose | What it does not do |
| --- | --- | --- |
| Request ID | Identifies the submission attempt, including a rejection before job creation. Retrying the same account, endpoint, ID, and payload avoids creating a duplicate evaluation. | Does not restart a terminal failed evaluation. |
| Evaluation ID | Identifies a remote run for status, waiting, diagnostics, logs, and its retained result. | Does not restart interrupted research. |
| Local run ID or local run path | Locates the local records used as evidence. | Is not an official remote evaluation ID. |
| Evidence digest / source digest | Identifies the exact uploaded evidence / harness source. | Is not a login credential or a checkpoint. |
| Yukon submission ID / job ID | Identifies leaderboard publication / its processing job. | Is not the research execution itself. |
| Correlation ID / edge ID | Helps operators locate a particular HTTP request and its rejection. | Cannot be used with `remote wait`. |

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
retry the **original submit command with unchanged inputs and the same state**.
The CLI reuses the saved request ID. Do not create a new request to work around
an uncertain outcome; the original may already be running.

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
the accepted attempt is waiting for the service to become available, not
necessarily that the harness is making model calls. Keep waiting on that
evaluation ID, or cancel it if you no longer want it to run. If progress appears
stuck, give the operator the evaluation ID. Do not submit a duplicate run.

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

## A candidate passed, but final verification or saving failed. Did I lose it?

Read the [separate execution and verification outcomes](submission-states.md#current-separate-outcomes).
An execution failure can coexist with a passed verification of a retained circuit;
if you have a valid receipt, follow publication recovery rather than restarting research.

An intermediate valid candidate, final verification, and a published result are
different outcomes. Keep the evaluation ID and diagnostics. Retained candidate
artifacts may allow operator recovery, but a score in stdout is not a verified
receipt, and verification-only retry is not a general solver command today.
Ask whether the existing result can be recovered **before authorizing another
research run**. Do not edit a receipt or manually insert a score.

For local testing, a failed or cancelled ended run can still qualify as evidence
when its model exchanges and settled accounting are complete and the remaining
checks pass. Conversely, wrapper exit code zero does not prove that the agent
succeeded. See [local outcomes and diagnostics](local-evaluation.md#local-outcomes-and-diagnostics).

## Verification succeeded, but Yukon publication failed. Must I rerun research?

This is a publication problem, not a transition back from `completed` to `running`.
OpenRSI currently reports leaderboard delivery as `not_confirmed` or
`receipt_delivered`; neither proves that Yukon's publication job succeeded.
Check the Yukon submission/job separately. Source publication also does not prove
leaderboard publication. See [publication outcomes](submission-states.md#current-separate-outcomes).

No. Preserve the verified receipt and inspect the existing Yukon submission/job.
Publication and Git branch errors do not invalidate an otherwise verified research
result. The publication path can use that receipt again without model inference.

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

When contacting the operator privately, start with only these identifiers and
error details. The operator should inspect the records already held by the
service first; you do not need to attach source, evidence, logs, or transcripts.

```text
Request ID / evaluation ID (whichever exists):
Yukon submission/job ID (if publication failed):
Approximate time of failure (UTC):
HTTP status and error code, if shown:
Correlation/edge ID, if no request or evaluation ID is available:
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
