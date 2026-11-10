# For agents

Build a research harness **with the human**, test it locally, then submit an
authorized remote run. For setup, use [Local setup and testing](local-setup-and-testing.md); follow only
the chosen provider recipe. Read other references when the current step needs them.

## Start with a conversation

In your first reply, before lengthy setup or implementation, explain the challenge
in a few plain-language sentences. A harness is an autonomous agent's prompts,
tools and research loop. ECDSA.fail asks it to build correct reversible circuits;
lower verified scores at the same model-credit usage are better. Do not assume
the human read the copied prompt or knows the problem. Invite questions.

Reuse an idea already supplied. Otherwise ask what the human would like to
explore: their own idea, an existing open-source agent or harness, a published
paper or blog post they are curious about, or a simple starting point you can build together.
These are starting points, not a fixed menu. Invite a link or an unfinished idea;
no prepared proposal is needed. Unless they already supplied an approach, explicitly
offer exploring a published paper or blog post in your first question: they can
share a link or ask you to find one about general-purpose research agents. Do not
replace these starting points with only a list of agent architectures. If they
are unsure, offer a few varied suggestions with brief tradeoffs.
Inspect any chosen paper, blog post or repository before claiming
what it implements; check reuse rights and adapt only general-purpose agent
methods, not problem-specific solutions. Wait for their choice before implementing.
If the human asks you to choose or work independently, respect that preference.
Ask for model access and testing budget only when missing.

While discussing, independent environment checks may run in the background;
delegation is optional when supported and permitted. Stay available for questions.
Do not spend model credits or implement a design before the relevant choices and
authorization. The human should not have to perform routine setup work.

## Show the journey

Show this compact status card in your first reply and at phase changes; do not merely describe it or keep it internal. Render it as a bordered card inside a monospace code block, not inline prose. Keep it narrow for phones; use no animation or terminal controls. Before the CLI is installed, use the discussion card below without delaying the first conversation. Mark only phases supported by evidence or the human's actual decisions.

```text
┌──────────────────────────────────────┐
│ OPENRSI · RESEARCH STATION           │
│                                      │
│ ● Choose an idea                     │
│ ○ Prepare the harness                │
│ ○ Test locally                       │
│ ○ Review readiness                   │
│ ○ Verify remotely                    │
│ ○ Explore results                    │
│                                      │
│ Now: Choosing an approach together   │
│ You: Share an idea or paper/blog     │
└──────────────────────────────────────┘
```

Once the CLI is installed, run `openrsi-space journey status --json` after setup and at run transitions or failures. For a known run, use `--local-run PATH` or `--evaluation ID` with the original global `--state PATH`. This command reads local records or checks an existing remote evaluation; it never starts, retries or publishes research. If several runs exist, select the one under discussion rather than guessing. Remote status needs the existing Yukon login and the same evaluator URL.

The collection is My research station: one harness card with its local and remote runs listed inside. Use `openrsi-space journey list --json` for the workspace overview, and `openrsi-space journey status --harness HARNESS_ID --json` to open a harness card. Select a run with `--local-run PATH` or `--evaluation ID` to show its progress inside that card. Translate requests such as “back to my station” or “open Paper Explorer” into these commands. Display numbers are temporary shortcuts; resolve them to the IDs in the latest output. Overview and harness lists use saved records without remote polling; only a selected remote evaluation is refreshed. This is a workspace-local collection, not an account-wide cloud library. Runs are grouped by recorded harness identity and source bindings, never by guessing from titles. Unknown identities stay separate. Each run keeps its own spending and outcome.

Show the returned `card` in a monospace code block in your chat reply: tool output may be hidden in desktop or phone apps. Explain the next action briefly. The CLI cannot know human choices or prove that setup is complete; add that conversational context without overriding observed execution, verification or usage. Saved local status can be stale; unknown usage is not zero. A completed phase means the attempt ended, not that its result was valid. If the command is unavailable in an older client, use the existing local records or remote status and mention the limitation; do not delay the conversation or upgrade silently. Keep the full card to phase changes and use short text updates between them. During remote waiting, use the existing `remote wait`; do not add a competing poll loop. No card or status check authorizes another paid run.

## Work through these stages

| Stage | Your job | Ready to continue when |
| --- | --- | --- |
| Choose an approach | Explain the challenge and discuss general-purpose harness designs. | The human chose an approach or explicitly asked you to choose. |
| Prepare | Reuse the human's idea, model choice and total testing budget. Inspect tools and existing login; install missing supported tools. | Docker works, model access is configured, and the harness builds. |
| Test locally | Run the autonomous harness from the assigned scaffold within the authorized budget. | Execution ended; original records and settled model exchanges are retained. A valid circuit is not required for evidence eligibility. |
| Ready for remote | Report source digest, problem tag/digest, provider/model/reasoning, recorded cap, actual usage, verification and unresolved errors. | Matching evidence is complete and the human authorized remote execution, private evidence review and public source release. |
| Verify remotely | Follow [submission commands](solver-guide.md#3-submit-for-remote-verification), using `--local-run PATH --platform-funded --wait`. | The existing evaluation reaches a terminal state and its verification outcome is known. |
| Result | Report score, usage, diagnostics and dashboard link when available. | The human knows the result and next action. Optional Yukon publication reuses the receipt; it needs no research rerun. |

In the first reply, briefly explain the journey: choose an idea together →
prepare the harness and local setup → test locally → review readiness → verify
remotely → discuss results. Say which phase you are in now. At each transition,
name the new phase, its purpose and what needs to happen before moving on.
Keep progress updates short: current phase, current work, measured usage/result
when available, and whether the human needs to act. Distinguish background setup
from the current discussion; starting another phase does not complete the first.
When returning to an earlier phase to fix something, explain why rather than
presenting it as starting over. Do not invent progress or usage.

When blocked, give one exact human action and explain why. Do ordinary
setup yourself; do not ask the human to assemble instructions from several docs.
Ask only for missing decisions. A login is not spending authorization; reuse
explicit permission, and count failed attempts against the total testing budget.

Before submission, read the [state model](submission-states.md). Keep execution,
verification and publication separate: `completed` alone does not prove validity.
Every remote run, including unsuccessful runs, is publicly listed under the solver's
username. Eligible source is public; local evidence is private and reviewed by a
third-party LLM. Never send personal model credentials to the remote evaluator.

## Discuss the first local test

Give a short debrief before moving on: what the harness tried (from its records),
validity and best score if any, model credits used, and one surprising result or
failure. Explain their meaning and distinguish measured facts from hypotheses.
Offer two concrete next experiments with tradeoffs and invite questions or a
preference. If the human already authorized proceeding remotely without another
pause, give the debrief and continue. Another experiment needs applicable spending
authorization. Never invent results or promise an improvement.

Collaborate before and between runs. During a measured run, the harness works
autonomously: do not inject human hints, edits or candidate solutions. Do not bundle
problem-specific strategies or discussion notes into the harness. Improve the
general-purpose search, tools, memory and evaluation behavior instead.

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
  `src/point_add/`; put notes elsewhere. See [source rules](source-and-build-rules.md).

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
