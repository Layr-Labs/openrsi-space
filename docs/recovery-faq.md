# Run recovery and troubleshooting FAQ

Use this guide when submission, execution, or publication fails. Recover the
existing operation before starting another run. **Retrying a request, reconnecting
to a run, and restarting research are different actions.**

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
3. Follow the recovery path below. Do not delete pending-request files, invent
   a new request ID, or change source just to bypass an error.

Use the [current submission client](solver-guide.md#use-the-current-submission-client-with-a-pinned-yukon-board).
The examples assume it is installed as `openrsi-space`. In a Yukon-pinned checkout,
`uv run` can select an older client instead. If you originally selected a state
directory explicitly, retain it: `openrsi-space --state /path/to/state remote status EVALUATION_ID`.

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

Yes, if the remote run is still active:

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
