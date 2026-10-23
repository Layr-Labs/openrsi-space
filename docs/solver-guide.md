# Catalyst: guide for solvers

## Select the current problem release

Before preparing a new evaluation, run `uv run catalyst problem current`. This
queries the official evaluator without credentials and reports its active release
and exact problem digest. If the installed package does not match, update your
Catalyst checkout/package and rerun the command. Do not assume a remembered tag or
a repository default is the deployed version. Use the returned tag explicitly as
`--problem-release TAG` for both `local run` and `remote submit`, and recheck it
before submission. Include the tag and digest in the readiness report.

Inside the run, read the server-assigned description and knowledge-base URLs from
`CATALYST_TASK`; never hardcode a versioned resource URL in a general-purpose
harness. Every new evaluation starts fresh with that release's scaffold and
resources. Preserve the original version and request ID when resuming an existing
run; a new release requires a new evaluation, not editing saved requests or receipts.

Catalyst is a benchmark for research agent harnesses. You submit your own
harness, using your own model account, to run in a controlled environment on
Catalyst's servers so that its performance can be independently verified and
compared with others on a public leaderboard.

You start each run, choose its spending and time limits, and can monitor its
progress or request cancellation through the CLI at any time while it is active.

Catalyst receives temporary model access for the run you start. When you use a
supported login handoff, your refresh credentials stay on your device. Supplied
access tokens are discarded during run cleanup. If you use an API key, Catalyst
uses it only for the run you start and removes it during cleanup.

You are responsible for ensuring your use complies with your model provider's
terms.

The default starting workspace is a **blank point-addition scaffold**, with
neutral helpers for registers, gates and wire allocation. It contains no
point-addition algorithm and has no valid baseline score. Your agent must build
and verify its first circuit, then retain improvements. Submit a general-purpose
harness. The task service supplies 40 bundled research papers to all runs; do not
include ECDSA-specific papers, strategies, notes or prewritten answers in source.

## Before you participate: your account, your model usage

Running `catalyst remote submit` with a model-credential option authorizes
Catalyst to receive that credential over HTTPS and use it for the remote run
under your selected provider, models, spending cap, and time/token limits.
This grants model access to the remote service; it is not just a local login
or an upload of your source.

Choose the cap before running the command. Subscription allowance and normalized
benchmark credits are different from actual cash charges. A final in-flight
response can exceed the cap; it is not a guaranteed provider billing limit.

Your **Yukon key identifies you**. Your **model credential permits inference on
your account**. The returned **receipt identifies the verified result**.
These are three separate things. Keep model credentials out of chat, source
code and public notes; use the CLI's private credential inputs.

A coding agent must obtain your authorization for remote credential use and the
spending cap before launching a run. Installing tools or finding an existing login
does not grant it. See [model access](live-models.md) for credential inputs.

## Participation flow

**The flow:** build your autonomous agent → test locally with Dungeness → review
readiness and approve a remote run → evaluate it on Catalyst → get a receipt →
submit that receipt to Yukon. Model-enabled local tests and remote evaluations
consume your model allowance; checking or publishing a receipt does not run
the agent again.

Want a coding agent to do the setup? Give it [the agent instructions](agent-prompt.md)
and your provider, model and spending cap. Keep model credentials out of the prompt.

## What the scores mean

| Matrix column | Result shown |
| --- | --- |
| Within $10 | Best verified `avg_toffoli × peak_qubits` achieved at or below 10 model credits |
| Within $20 | Best verified result achieved at or below 20 model credits |
| Within $50 | Best verified result achieved at or below 50 model credits |
| Within $100 | Best verified result achieved at or below 100 model credits |
| Best overall | Best verified result anywhere in your run |

Lower is better. You choose a finite spending cap; the columns are views of
one run's history, not separate paid runs. A $3 run can appear in all five
columns. An improvement first achieved at $25 cannot count in the $20 column.
Missing observations display as `—`, never zero.

Each cell shows credits **when that score was achieved**, which can be less
than total run usage. Yukon uses the Pareto pair
`[best verified performance, credits when achieved]`. A frontier result is
unbeaten on both objectives. The progress view keeps verified regressions too.
Failed or invalid attempts remain in evaluation records and are not ranked.

Credits use pinned reference model prices. Subscription usage can consume
your allowance without a separate cash charge. Infrastructure costs are
separate. Token and time limits can stop a run before its credit cap.
An in-flight model response can overshoot the cap; Catalyst retains actual
usage and, under validity policy v3, accepts overshoot with trusted evidence
that every charged request started before budget exhaustion. See [accounting details](tier-accounting.md).

## 1. Install and connect

You need Git, [uv](https://docs.astral.sh/uv/getting-started/installation/),
Python 3.11 or newer (uv can install Python), and a current Yukon CLI.
For the recommended preflight, install and start Docker and clone the public
[Dungeness repository](https://github.com/Layr-Labs/dungeness) to any location.
Dungeness coordinates the harness, model gateway, problem service and evaluator
in containers. Catalyst prepares and starts them with `catalyst local run`;
no manual server setup or private repository is needed. Read the
[architecture](architecture.md) and [local testing procedure](local-evaluation.md).
Local scores help development; official results require a remote receipt.

**Current MVP environment:** Yukon dev, benchmark `layr-labs/catalyst`,
verifier `https://3.21.93.126`. Use a dev Yukon account/key; a production
key from `www.yukon.org` does not work against this service. While the
repository is private, your GitHub account also needs read access.

```sh
export YUKON_API_URL=https://api-dev.yukon.org
export CATALYST_EVALUATOR_URL=https://3.21.93.126
curl -fsSL https://api-dev.yukon.org/yukon/install.sh | sh
```

Reuse an existing Yukon dev CLI login. Otherwise, create a key on the dev
website's **API keys** page and enter it at a hidden terminal prompt:

```sh
read -r -s YUKON_API_TOKEN
export YUKON_API_TOKEN
```

Do not put the key in a source file, submission note or chat. Then:

```sh
yukon clone layr-labs/catalyst catalyst-solver
cd catalyst-solver
uv sync --frozen
yukon setup
```

If you already have a clone, work in its printed benchmark directory and
preserve local edits before updating. This is one schema-v1 benchmark; there
are no budget tracks to switch between.

## 2. Prepare a harness

The assigned problem now includes a human-readable release (`v1`) alongside its
content hash. During execution, use `CATALYST_DESCRIPTION_URL` for the versioned
description and `CATALYST_KNOWLEDGE_BASE_URL` for the resource catalog. Follow
catalog URLs and media types; the knowledge base can contain material beyond
PDF papers. See [the endpoint contract](generic-harnesses.md#versioned-problem-and-knowledge-base-endpoints).

Your package can contain general-purpose source, prompts, helper programs,
configuration and a Dockerfile with pinned dependencies. You can
use your own agent architecture, subprocesses or search framework.

To generate an editable starter:

```sh
uv run catalyst harness create my-agent --title "YOUR CHOSEN NAME" --output .catalyst/my-harness
```

Replace the title placeholder with a short, distinctive name for your harness's
general-purpose approach, usually 2–5 words. Your coding agent should propose a
name if you have not chosen one. Use the same name in `harness.json.title`, your
submission note and `yukon-submit --harness`; the `my-agent` ID is only a slug.
Keep the name across retries and model/budget changes, and add a version for
meaningful harness changes. Avoid generic placeholders, timestamps, run IDs,
spending caps and unverified performance claims in the display name. Describe
the approach and credit upstream work separately. See the
[agent naming instructions](agent-prompt.md#choose-the-harness-name), including
how to name direct repository submissions in the source catalog.

The starter checks its assigned workspace and makes no model calls. Replace
`agent.py` with your autonomous solver and install its dependencies in the
Dockerfile. You can instead submit your own agent repository directly; there
are no bundled example harnesses to copy.
Choose the matching model client and credential method; changing a provider
flag does not convert an agent to a different API protocol.

For an existing repository without `harness.json`, provide a Dockerfile and
`--entrypoint`. For example:

```sh
uv run catalyst remote submit /path/to/your-agent \
  --entrypoint "python3 /app/main.py" \
  --provider PROVIDER --model EXACT_MODEL --budget 3 \
  --no-token-limit --max-seconds 10800 \
  --prompt-model-token --wait
```

**That command starts an evaluation.** Run it only when your source and
chosen spending cap are ready. The entrypoint must match your Dockerfile.
Do not combine `--entrypoint` with an existing `harness.json`.

Runtime requirements:

- Install generic dependencies in the image. The research container has no
  public internet access. Read `CATALYST_KNOWLEDGE_BASE_URL` for the shared
  eight-paper catalog and internal PDF links. Do not bundle task-specific material.
- Read `CATALYST_TASK` for the problem instruction, writable workspace,
  candidate paths, declared models and metered gateway endpoints. Route every
  model request through those endpoints. Do not hard-code public provider URLs.
- Call `evaluate --json PATH` on candidate snapshots during research so
  intermediate progress is recorded. Retain the best candidate in the designated
  workspace for final independent verification. Text claiming a score is not evidence.
- Keep all credentials outside the source directory. The source archive is
  limited to 8 MiB and cannot contain symlinks. `.env*`, Git metadata, local
  state and virtual environments are excluded; these exclusions do not replace
  checking your own source for secrets.
- Declare models and choose spending caps and timeouts deliberately. Token
  ceilings are optional and disabled by default; tokens remain metered. The service must
  support the provider protocol and resolve reference pricing before inference.
  The current VM enables `openai-chatgpt`, `xai` and
  `grok-subscription`; arbitrary model names do not imply arbitrary provider
  protocols are available.

See [the generic harness contract](generic-harnesses.md) for model ensembles,
packaging, pricing and gateway details.

## 3. Test locally before submitting

Use [the local Dungeness workflow](local-evaluation.md) with your chosen harness,
current problem release and a clean runtime checkout. Start with `--prepare-only`
to build without model calls, then authorize a separate local budget and execute
the full harness. Preparation and smoke checks alone do not test model/tool
calls, candidate evaluation or recovery after failures.

Inspect startup, tool calls, workspace edits, evaluation responses, model usage
and clean shutdown. Fix failures and repeat with fresh memory and the assigned
scaffold; do not copy local candidates or task-specific notes into your harness.
Record the runtime revision, release, checks and total usage across retries.
Local testing does not reproduce private screening or guarantee remote acceptance.
If it is blocked or you decline it, explicitly identify untested steps before
proceeding. This is the standard workflow, not an API-enforced submission gate.

## 4. Supply model access and evaluate

Review the prepared harness and its local checks first. If a coding agent is
helping, it should report what it built, what it tested, and the proposed model
and limits, then wait for your approval to run unless you already authorized
execution once ready. You decide when the harness is ready for remote evaluation.

**The commands below grant Catalyst remote access to your model account for
this evaluation and consume your credits or subscription allowance.**
Run them only when you authorize that use and have reviewed the spending cap.

These are separate credentials and outputs:

| Item | Purpose |
| --- | --- |
| Yukon dev login/key | Identifies you to Catalyst and Yukon |
| Model access | Lets this evaluation use your provider/subscription allowance |
| `verification.json` receipt | Refers to the completed evaluation, source and problem; it is not a login key |
| GitHub OIDC | Authenticates Yukon's verification workflow automatically; you do not supply it |

For your prepared harness, choose a compatible provider and exact model, then
submit using the hidden credential prompt:

```sh
uv run catalyst remote submit .catalyst/my-harness \
  --provider PROVIDER --model EXACT_MODEL --budget 3 \
  --no-token-limit --max-seconds 10800 \
  --prompt-model-token --wait
```

Replace `PROVIDER` and `EXACT_MODEL` with values supported by both your harness
and the service. Enter the matching model credential at the hidden prompt.
The $3 cap is an example, not a required challenge budget or spending target.

New evaluations have no model-token ceiling by default. `--no-token-limit`
clears any ceiling saved in an older `evaluation.json`; use `--max-tokens N`
only if you want an additional token allowance. Tokens are still metered for
credit accounting. Spending caps and execution timeouts remain enforced.
New evaluations default to 10,800 seconds (3 hours). The current service accepts
up to 21,600 seconds (6 hours) with `--max-seconds 21600`.
These examples also override any shorter time limit saved in an existing
`evaluation.json`. Use `--max-seconds` to request a shorter run if desired.

For a Codex/ChatGPT harness instead:

```sh
uv run catalyst remote submit .catalyst/my-harness \
  --provider openai-chatgpt --model gpt-6-astra \
  --reasoning-effort high --budget 3 \
  --no-token-limit --max-seconds 10800 \
  --codex-auth-file --wait
```

`--codex-auth-file` reads an existing local `~/.codex/auth.json` and sends its
temporary access material to the remote service; it is not local-only.
No manual token extraction is needed. You can supply an explicit path. See
[model login setup](live-models.md#first-time-login) if the file is absent.
A submitted Codex harness has completed remote execution and independent
verification with no model-token ceiling. Your own harness still needs to
match the selected provider's API and tool definitions; see
[harness compatibility](harness-compatibility.md).

Credentials travel over authenticated HTTPS, remain temporary in service
memory/tmpfs, and are excluded from persisted jobs, receipts and artifacts.
Refresh credentials stay on your machine. Supply secrets through the hidden
prompt, stdin or a private credential file outside your source package.

The CLI prints an **evaluation ID**. Keep it:

```sh
uv run catalyst remote status EVALUATION_ID
uv run catalyst remote wait EVALUATION_ID
```

These commands resume retrieval of the same evaluation. Do not resubmit just
because a wait or connection was interrupted: a fresh submit after completion
starts another run. A service restart cannot resume active research automatically.

## 5. Retrieve and inspect the receipt

After a successful `--wait`, Catalyst prints the validity, score pair,
evaluation ID, private artifact paths and receipt path. Normally the receipt
is `.catalyst/my-harness/verification.json`. Use the exact printed path if
the source changed while the run was in progress.

Continue only with a valid verified result:

```sh
mkdir -p submission
cp .catalyst/my-harness/verification.json submission/verification.json
yukon run
```

Copy the **whole receipt unchanged**. Do not extract a token field, edit a
score, or copy another solver's receipt. Catalyst checks the stored evaluation's
owner, problem and source identity. Editing your local harness afterwards
does not change what this receipt refers to.

`yukon run` retrieves the existing result; it does not build or execute the
harness again. A local claimed score cannot substitute for a verified receipt.

## 6. Publish to Yukon

Write `submission-note.md` before submitting. Yukon requires a public note
of 5–100 KiB. Explain the harness, knowledge/dependencies, exact model and effort,
spending/token/time caps, commands, experiments, measured results, failures and
limitations. Record cost at the best result separately from total usage.
Exclude secrets, personal data and private local paths. Do not pad with
invented experiments to meet the length requirement.

Publish with the exact model and harness attribution for your run:

```sh
uv run catalyst yukon-submit --note-file submission-note.md \
  --model "EXACT MODEL" --harness "HARNESS NAME" --no-dependencies
yukon submissions --all --json
```

Use your actual model and harness. If reusing an earlier Yukon submission,
replace `--no-dependencies` with `--dependencies-file dependencies.json`,
following `yukon skill`.

**Use `catalyst yukon-submit` for this challenge.** It invokes stock
`yukon submit` and registers the resulting execution/receipt binding with
Catalyst. Plain `yukon submit` alone does not complete that binding.
If binding fails, repeat the same helper command to resume its saved operation;
follow its recovery message if the upload outcome is unknown.

Yukon creates a candidate commit and runs Catalyst's GitHub Actions workflow.
The workflow authenticates to the verifier and fetches the existing verified
score and curve. No second research run occurs. **Pareto submissions are
recorded without merging solution code.** The submission ID in Yukon differs
from the remote evaluation ID.

The matrix reads official scores from Yukon. It does not trust scores in
your note or enumerate GitHub branches. The `/catalyst` UI is implemented
locally and awaits hosting; until then, inspect results with the CLI.

## Download or share your work

New remote submissions require public harness source, published after the run
stops and publication screening passes. Review files before submitting; private
submissions and solver unpublication are not supported. Traces are retained internally and cannot be downloaded or published.
No license is granted automatically: use `--source-license MIT` (or another supported
license) only when you have authority to grant it. Existing private runs stay private.
With the same Yukon account:

```sh
uv run catalyst remote download EVALUATION_ID --kind harness --output harness.zip
```

This downloads the original evaluated harness source. Runtime traces and
complete evidence bundles are retained internally and are not downloadable.

To publish source from a run you kept private, or add an authorized license:

```sh
uv run catalyst remote publish EVALUATION_ID --harness --confirm-source-reviewed
```

First download and review the exact harness ZIP. You are responsible for the
source, prompts and knowledge files you choose to make public and for having
permission to share them. Credential screening still applies and cannot be waived.
A license is optional; add `--license` only for a grant you have authority to make. See [artifact sharing](artifact-sharing.md)
for downloads, license choices and publication of historical source.

## Challenge rules

Catalyst evaluates **autonomous research**, not the replay of an existing answer.
Harnesses that fetch, search for, bundle, or reproduce existing ECDSA GitHub or
leaderboard solutions are prohibited and are rejected when detected. This
includes asking the agent to recall a memorized submission, embedding it in
prompts or knowledge files, and disguising it as an answer cache or dependency.
Removing attribution, changing formatting, or disabling internet access does
not make reuse permitted.

Use the assigned task, blank scaffold and shared paper library. Ordinary
frameworks and general-purpose tools are allowed. Submitted problem-specific
papers, citations, notes, circuit strategies, cached answers and prewritten
candidates are prohibited, whether original, copied or public. Incidental
problem IDs and interface paths are allowed when they contain no solution knowledge.
Do not access host resources, tamper with the verifier or bypass metering.
Candidate source must satisfy the pinned verifier and screening rules.

The published-solution screen refreshes the official repository's branches and
open/closed pull-request heads before a remote run. Substantial matching source
including historical baseline code blocks the run before build or solver model usage. The
rejection reason and private `solution-corpus.json` report identify the harness
location and reference blob. A failed refresh blocks screening without declaring
cheating. The semantic source reviewer checks problem-specific material before
execution. Unavailable or inconclusive screening blocks execution; opaque files
that cannot be reviewed must be removed or provided as inspectable source.
Neither check proves originality or detects all memorization. See
[the screening policy and deployment status](cheat-filter.md).

If a job fails, inspect its reported reason before choosing whether
to spend on another evaluation. Do not fabricate a receipt or score to bypass
a failure.

### Submission limits and retries

Catalyst has no daily evaluation-count cap by default. It retains one active run
per account, eight globally, and short submission windows (five new evaluations
per account per minute; thirty globally). Operators can explicitly configure a
daily quota. Account identity comes from Yukon, so changing API keys does not
change these limits.

A 429 now identifies account concurrency, global capacity, submission rate, or an
explicit daily quota, with `limit`, `current`, and `retry_after_seconds`. Wait for
the indicated interval and rerun the same submission command using the same
`--state` directory, source and options. Catalyst reuses its saved request ID;
do not delete pending state or generate a new ID to retry. You do not need to
repeat local testing to resume the same unchanged request. Successful source reviews are reused when source, policy,
reviewer configuration and problem identity match.
