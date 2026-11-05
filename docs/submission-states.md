# Submission state model

Accepted remote results appear automatically on the OpenRSI dashboard. Remote
run status is public; only accepted, verified results receive ranked scores.
Yukon publication is optional: it adds an account-linked submission and repository
record without another research run. Stopping the CLI or revoking your Yukon key
does not remove an accepted result from the OpenRSI dashboard. Private local
execution evidence, raw logs and credentials are not part of the public feed.

This reference defines the evaluation lifecycle, separate outcomes and operation
identities. For diagnostic commands, retries and escalation, use the
[submission recovery guide](submission-recovery.md). For component responsibilities,
see [architecture](architecture.md).

The solver's overall journey is:

```text
local test → submission/admission → remote evaluation → verified result → automatic dashboard visibility
                                             └→ optional Yukon publication
```

Local evidence establishes readiness for admission; it is not an official score.
Each admitted remote evaluation starts fresh. Receipt publication uses a retained
verified result and does not start another research run.

## Current: admission and remote evaluation

Admission checks precede evaluation creation. A request ID identifies the submission
attempt. A confirmed admission rejection has no evaluation ID. A lost response
leaves acceptance unknown: an evaluation may already exist. Neither case is an
evaluation lifecycle state named `failed`.

Once admitted, the evaluation has a persistent ID and follows this normal path:

```text
queued → building → running → verifying → completed
```

| State | Meaning | Terminal? |
| --- | --- | --- |
| `queued` | Accepted and waiting to be claimed. | No |
| `building` | Preparing the run, including screening, building and startup. This does not establish that inference has begun. | No |
| `running` | Harness execution has started; usage separately indicates whether model calls occurred. | No |
| `verifying` | Processing and checking the run's result. | No |
| `completed` | Result processing finished. Completion alone does not mean a valid circuit. | Yes |
| `failed` | This attempt stopped with an error. | Yes |
| `cancelled` | This attempt was cancelled. Charges already incurred still count. | Yes |

Build, execution and verification can end in `failed` or `cancelled`. Queued
evaluations can also be cancelled. Cancellation of active work is a request;
acknowledging that request is distinct from reaching a terminal status.

Transitions are recorded durably and invalid transitions are rejected. An evaluation
does not transition from a terminal state back into active research. A new research
attempt has a new evaluation ID and its own spending authorization and limits.

Worker interruption ends started work as failed (or cancelled if requested);
recovery does not automatically replay potentially paid calls. Missing or expired
model access also ends the attempt rather than pausing it for replacement credentials.
There is no general remote checkpoint-resume operation.

## Current: separate outcomes

The evaluation lifecycle describes the attempt as a whole. Its execution,
verification and publication outcomes answer separate questions:

| Dimension | Field in owner diagnostics | Current outcomes | Meaning |
| --- | --- | --- | --- |
| Execution | `outcomes.execution` | `not_started`, `running`, `completed`, `failed`, `cancelled` | What happened to the harness execution. A retained circuit can sometimes verify even after the harness failed. |
| Verification | `outcomes.verification` | `not_started`, `running`, `passed`, `rejected`, `failed`, `cancelled` | Whether the result was checked and valid. An invalid candidate and a failure of the checking process are different outcomes. |
| Source publication | `outcomes.publication.source` | `pending`, `published`, `blocked`, `retryable_failure` | Availability of the evaluated harness source under the source-publication policy. |
| Server receipt delivery | `outcomes.publication.leaderboard` | `not_confirmed`, `receipt_delivered` | What the verifier knows about delivery toward the leaderboard. Neither outcome confirms optional Yukon acceptance; neither controls automatic dashboard visibility. |

The owner status response nests this report under `diagnostics`, so the equivalent
verification field there is `diagnostics.outcomes.verification`. The standalone
outcomes API uses protocol `openrsi-outcomes-v1` and returns these fields without
the `outcomes` wrapper. Its `receipt_available` flag currently reflects lifecycle
status `completed`; it does not establish `valid: true` or leaderboard eligibility.

These are reported outcomes, not four independently retryable execution engines.
In particular:

- An execution failure is distinct from the overall evaluation status `failed`.
  A retained candidate can verify after the harness fails. The public client requires
  overall status `completed` and a validated result to export a receipt through `wait`.
- `completed` does not imply `valid: true`. An intermediate candidate check, final
  result validity and a verified receipt are separate evidence.
- Published harness source does not imply a verified score or leaderboard acceptance.
- Receipt delivery does not imply Yukon publication. Publication failure does not
  transition a completed evaluation back into research.
- A terminal evaluation does not by itself establish complete accounting or released
  funding reservations. Missing usage can prevent receipt issuance even if a candidate passed.
- Missing outcome fields in an older report mean unavailable information.

### Client publication states

The CLI's automatic-publication record tracks a separate operation from the
verifier's receipt-delivery outcome. Its state is reported as `state` by the
publication command and as `publication.state` in evaluation command output when present.

| Client state | Meaning |
| --- | --- |
| `not_requested` | Automatic publication was not selected. |
| `pending` | Waiting for verification or the next client publication attempt. |
| `submitting` | An upload may have reached Yukon; its outcome may still be uncertain. |
| `awaiting_yukon` | Yukon has the submission and its outcome is being checked. |
| `published` | Yukon reports the submission accepted. |
| `needs_authentication` | The saved publication needs the same owner's valid local login. |
| `retryable_failure` | Publication is incomplete and its reported issue needs resolution. |
| `not_eligible` | The evaluation ended without an eligible verified result for automatic publication. |

These labels are not remote evaluation lifecycle states. Publication runs in the
client using local authentication; stopping the client does not cancel remote
research. Yukon submission/job IDs identify the downstream publication operation.
The [publication recovery guide](submission-recovery.md#verification-succeeded-but-yukon-publication-failed-must-i-rerun-research)
maps these states to actions.

<a id="current-identifiers-and-safe-retries"></a>

## Identifiers and operation identity

| Identifier | Meaning | Boundary |
| --- | --- | --- |
| Request ID | Identifies a submission attempt. The same account, endpoint, ID and payload identify an idempotent request. | Reusing it does not restart a terminal evaluation. |
| Evaluation ID | Identifies one admitted remote research attempt and its retained result. | Retrieval does not restart execution. |
| Local run ID or path | Identifies the local records used as readiness evidence. | Local results are not official remote scores. |
| Evidence digest / source digest | Identifies the exact evidence bundle / harness source. | Neither is a login credential or execution checkpoint. |
| Yukon submission ID / job ID | Identifies leaderboard publication and its processing job. | Neither is the remote research evaluation ID. |
| Correlation ID / edge ID | Identifies an HTTP request for diagnosis, including errors without an evaluation ID. | Neither identifies a resumable research attempt. |

Recovering a pending submission preserves its request identity and unchanged
payload. Retrieving an evaluation preserves its evaluation identity. Retrying
publication uses the retained receipt and publication identity. Starting fresh
research creates a new attempt and can incur new charges.

The CLI's saved state binds these identities to the endpoint, owner operation,
source and settings. Repeating the same shell command is not itself an identity
guarantee: whether the client still has a pending request matters. The
[recovery guide](submission-recovery.md#how-do-i-start-a-new-attempt-after-a-terminal-result)
documents that client behavior and the procedure for a deliberate new attempt.

## Related guides

<a id="publish-a-verified-receipt"></a>

- [Publish a verified receipt](submission-recovery.md#publish-a-verified-receipt).
- [Diagnose a failure and choose a recovery action](submission-recovery.md#which-recovery-path-matches-my-submissions-state).
