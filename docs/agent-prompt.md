# For agents

Build the human's research-agent idea, test it locally, then submit an authorized
remote run. Start with [Local setup and testing](local-evaluation.md); follow only
the chosen provider recipe. Read other references when the current step needs them.

## Work through these stages

| Stage | Your job | Ready to continue when |
| --- | --- | --- |
| Prepare | Reuse the human's idea, model choice and total testing budget. Inspect tools and existing login; install missing supported tools. | Docker works, model access is configured, and the harness builds. |
| Test locally | Run the autonomous harness from the assigned scaffold within the authorized budget. | Execution ended; original records and settled model exchanges are retained. A valid circuit is not required for evidence eligibility. |
| Ready for remote | Report source digest, problem tag/digest, provider/model/reasoning, recorded cap, actual usage, verification and unresolved errors. | Matching evidence is complete and the human authorized remote execution, private evidence review and public source release. |
| Verify remotely | Follow [submission commands](solver-guide.md#3-submit-for-remote-verification), using `--local-run PATH --platform-funded --wait`. | The existing evaluation reaches a terminal state and its verification outcome is known. |
| Result | Report score, usage, diagnostics and dashboard link when available. | The human knows the result and next action. Optional Yukon publication reuses the receipt; it needs no research rerun. |

Announce each stage, whether model usage has begun, and meaningful progress or
errors. When blocked, give one exact human action and explain why. Do ordinary
setup yourself; do not ask the human to assemble instructions from several docs.
Ask only for missing decisions. A login is not spending authorization; reuse
explicit permission, and count failed attempts against the total testing budget.

Before submission, read the [state model](submission-states.md). Keep execution,
verification and publication separate: `completed` alone does not prove validity.
Every remote run, including unsuccessful runs, is publicly listed under the solver's
username. Eligible source is public; local evidence is private and reviewed by a
third-party LLM. Never send personal model credentials to the remote evaluator.

## Essential harness rules

- Build general-purpose agent machinery. Read the assigned task and resources at
  runtime; do not bundle ECDSA solutions, strategies, papers or answer caches.
- Never alter traces, usage, evidence, saved requests or receipts to pass checks.
  Preserve attribution. Do not select an additional source license unless asked.
- Install dependencies in the image. Use assigned gateway routes and model settings;
  changing a model name does not adapt an API. Public internet, hosted search and
  model image inputs are unsupported. Your local tools can extract document text.
- Handle gateway errors in the wrapper: stop for `run_action=stop`; use bounded
  backoff for retryable errors; correct the request for `continue` with
  `retryable=false`. A CLI exit is not feedback delivered to the model. Preserve
  pending evaluation results and the best candidate. See [Build a harness](executable-harness.md).
- Keep mount roots and trusted files intact. Restore checkpoint contents into the
  existing candidate path. For ECDSA, only UTF-8 Rust source belongs in
  `src/point_add/`; put notes elsewhere. See [source rules](source-limits.md).

## Diagnose before restarting

Use [Troubleshooting](submission-recovery.md), retained local records, or
`remote status`, `remote diagnostics` and owner-authenticated `remote logs`.
Preserve IDs and saved state. A terminal attempt cannot generally resume research;
do not start another paid run merely to repair publication or retrieve a result.

Return:

```text
State / failed stage:
Request or evaluation ID:
Execution / verification / evidence or publication outcome:
Cause: harness | platform | account/provider | unknown — evidence and safe error code
Next action: reconnect | correct harness | operator help | authorized new run
New model spending required: yes | no | unknown
```

Do not guess the cause. Keep keys, login files, private prompts and full traces out
of chat and support messages. Keep diagnostic files private unless sharing is
authorized. For authentication failures, follow the [private-terminal handoff](solver-guide.md#yukon-authentication-when-needed);
an already-running agent cannot inherit another terminal's environment.
