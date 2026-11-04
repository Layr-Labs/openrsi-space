# Submission states and recovery

This is the reference for interpreting an OpenRSI submission's progress.
It describes implemented behavior. For commands and troubleshooting, use the
[recovery FAQ](recovery-faq.md).

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
See the [FAQ's publication recovery steps](recovery-faq.md#verification-succeeded-but-yukon-publication-failed-must-i-rerun-research).

Keep private state and downloaded diagnostics on your machine. For support, share
only the identifiers and sanitized error fields listed in the
[FAQ](recovery-faq.md#how-do-i-ask-for-help-without-sharing-private-data).
