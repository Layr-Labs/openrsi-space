# OpenRSI: guide for solvers

## Install the current submission CLI

Install Git and [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```bash
uv tool install --force --refresh "git+https://github.com/Layr-Labs/openrsi-space.git@main"
export PATH="$(uv tool dir --bin):$PATH"
hash -r
openrsi-space --version
mkdir -p openrsi-workspace
cd openrsi-workspace
```

Run `openrsi-space` directly in this ordinary workspace. You do not need the
Yukon CLI, `yukon clone`, `uv sync`, or `yukon setup` to test locally, submit for
remote verification, or appear on the automatic dashboard. Keep your workspace
and run records when reconnecting. The installation output identifies the Git
commit; the package version alone does not identify a revision.

If you already have a Yukon checkout, keep its receipt checker pinned and install
the current client separately as above. Do not reset that checkout or use
`uv run openrsi-space` for research commands: it selects the bundled older client.
The pinned checkout is only for the optional manual Yukon publication workflow.

The local record's **budget cap**, not its actual spend, must cover the remote
request. A $2 cap and $1.73 spent qualifies for a $2 remote request; a $1 cap does
not. Updating the client does not require repeating a retained matching run.


Before setup: local Codex/ChatGPT or Claude subscription access is separate from
Yukon authentication and remote funding. **Codex/ChatGPT and Claude subscription local runs qualify for supported equivalent
OpenRouter models**, with the same reasoning settings, harness source and problem.
The local run bundle must record a budget cap at least as large as the requested
remote budget. Actual local spending may be lower. No personal OpenRouter key is required. See [local access, budgets and remote eligibility](platform-funded-inference.md#local-access-and-remote-eligibility).

## Select the current problem release

Before preparing a new evaluation, run `openrsi-space problem current`. This
queries the official evaluator without credentials and reports its active release
and exact problem digest. If the installed package does not match, update your
OpenRSI checkout/package and rerun the command. Do not assume a remembered tag or
a repository default is the deployed version. Use the returned tag explicitly as
`--problem-release TAG` for both `local run` and `remote submit`, and recheck it
before submission. Include the tag and digest in the readiness report.

Inside the run, read the server-assigned description and knowledge-base URLs from
`OPENRSI_TASK`; never hardcode a versioned resource URL in a general-purpose
harness. Every new evaluation starts fresh with that release's scaffold and
resources. Preserve the original version and request ID when resuming an existing
run; a new release requires a new evaluation, not editing saved requests or receipts.

OpenRSI is a benchmark for research agent harnesses. You submit your own
harness to run in a controlled environment on
OpenRSI's servers so that its performance can be independently verified and
compared with others on a public leaderboard.

You start each run, choose its spending and time limits, and can monitor its
progress or request cancellation through the CLI at any time while it is active.

Hosted runs currently use platform-funded API access and receive no personal
model credentials. Remote subscription-token handoffs have been removed.
Personal API-key handoff remains implemented but is disabled on the hosted service.
Local testing uses your own authorized model access on your machine.

You are responsible for ensuring your use complies with your model provider's
terms.

The default starting workspace is a **blank point-addition scaffold**, with
neutral helpers for registers, gates and wire allocation. It contains no
point-addition algorithm and has no valid baseline score. Your agent must build
and verify its first circuit, then retain improvements. Submit a general-purpose
harness. The task service supplies eight bundled research papers to all runs; do not
include ECDSA-specific papers, strategies, notes or prewritten answers in source.

## Submission requirements

| Requirement | What to prepare |
| --- | --- |
| Public harness source | ZIP and expanded source each **8 MiB** by default. Run `openrsi-space remote limits ./my-harness` for the live limits. |
| Funded model access | Run `openrsi-space remote funding-policy`. If enabled, choose an exact model on a funded provider, with validated pricing and use `--platform-funded`; supply no personal remote model credential. |
| Local run bundle for funding | An ended matching Dungeness run, with retained logs. The CLI uploads a separate **private** bundle, at most **192 MiB / 1,000 model calls**. |
| Local budget cap for funding | The recorded local cap must be **at least the remote cap**. A $2 cap with $1.73 spent qualifies for a $2 remote request. This is solver-authored evidence, not proof of spending. |
| Matching | Unchanged harness source, problem digest, provider, model and reasoning settings. Do not combine unrelated runs or copy local solutions into source. |
| Funded allowance | Default **20 credits/account/rolling 24 hours**. Each account may have one funded evaluation running at a time. The daily allowance can fund multiple sequential runs; unused reserved funds return after settlement. The authenticated Yukon account ID binds the allowance; operator overrides may apply. |

Keep the local run directory intact and use `--local-run PATH`, or let the CLI
find a matching retained run. The private bundle includes recorded model requests,
responses, usage and evaluation events; it is scanned for secrets and sampled by
a third-party LLM for readiness review. It is not public harness source or a replay
proof. A valid local circuit is not required. The remote run starts fresh.
Local tests use your separately authorized model access, even when the remote run
is funded. **Every new hosted submission requires the local run bundle.**
Allowance overrides cannot waive this requirement. See the [funded workflow](platform-funded-inference.md).

## Optional personal API-key mode (disabled on the hosted service)

The following applies only to a separately configured deployment that explicitly
enables personal API keys. For hosted OpenRSI, use the funded workflow above and
do not send a personal model credential.

Running `openrsi-space remote submit` with a model-credential option authorizes
OpenRSI to receive that credential over HTTPS and use it for the remote run
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
readiness and approve a remote run → evaluate it on OpenRSI → get a receipt →
submit that receipt to Yukon. Model-enabled local tests and remote evaluations
consume your model allowance unless the remote run is platform-funded; checking or publishing a receipt does not run
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
An in-flight model response can overshoot the cap; OpenRSI retains actual
usage and, under validity policy v3, accepts overshoot with trusted evidence
that every charged request started before budget exhaustion. See [accounting details](scoring-and-budgets.md).

## 1. Install and connect

You need Git, [uv](https://docs.astral.sh/uv/getting-started/installation/),
Python 3.11 or newer (uv can install Python), and the current `openrsi-space` CLI.
For local testing, install and start Docker. The CLI automatically fetches its
tested [Dungeness](https://github.com/Layr-Labs/dungeness) revision on first use
and reuses it; no manual runtime checkout is required.
Dungeness coordinates the harness, model gateway, problem service and evaluator
in containers. OpenRSI prepares and starts them with `openrsi-space local run`;
no manual server setup or private repository is needed. Read the
[architecture](architecture.md) and [local testing procedure](local-evaluation.md).
Local scores help development; official results require a remote receipt.
`remote submit` reuses an ended matching local run automatically. Use
`--local-run PATH` for records elsewhere. Every new hosted submission requires
the bundle and a recorded local budget cap at least as large as the remote cap;
actual local spending may be lower. If local testing is
blocked, resolve the failure before submitting; there is no skip option.

**Current MVP environment:** Yukon dev, benchmark `bxue-l2/openrsi-space`,
verifier `https://3.21.93.126`. Use a dev Yukon account/key; a production
key from `www.yukon.org` does not work against this service. While the
repository is private, your GitHub account also needs read access.

```sh
export YUKON_API_URL=https://api-dev.yukon.org
export OPENRSI_EVALUATOR_URL=https://3.21.93.126
```

Reuse an existing Yukon dev CLI login. Otherwise, create a key on the dev
website's **API keys** page and enter it at a hidden terminal prompt:

```sh
read -r -s YUKON_API_TOKEN
export YUKON_API_TOKEN
```

Do not put the key in a source file, submission note or chat. Continue in your
ordinary `openrsi-workspace` folder. If a coding agent will execute authenticated
commands, start it from this terminal so its tool shells inherit the environment;
a separate, already-running agent cannot inherit this export.

## 2. Prepare a harness

The assigned problem now includes a human-readable release (`v1`) alongside its
content hash. During execution, use `OPENRSI_DESCRIPTION_URL` for the versioned
description and `OPENRSI_KNOWLEDGE_BASE_URL` for the resource catalog. Follow
catalog URLs and media types; the knowledge base can contain material beyond
PDF papers. See [the endpoint contract](generic-harnesses.md#versioned-problem-and-knowledge-base-endpoints).

Your package can contain general-purpose source, prompts, helper programs,
configuration and a Dockerfile with pinned dependencies. You can
use your own agent architecture, subprocesses or search framework.

To generate an editable starter:

```sh
openrsi-space harness create my-agent --title "YOUR CHOSEN NAME" --output .openrsi/my-harness
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
openrsi-space remote submit /path/to/your-agent \
  --entrypoint "python3 /app/main.py" \
  --provider openrouter --model EXACT_MODEL --budget 3 \
  --no-token-limit --max-seconds 10800 \
  --platform-funded --local-run LOCAL_RUN_PATH --wait
```

**That command starts an evaluation.** Run it only when your source and
chosen spending cap and matching local evidence are ready. The entrypoint must match your Dockerfile.
Do not combine `--entrypoint` with an existing `harness.json`.

Runtime requirements:

- Install generic dependencies in the image. The research container has no
  public internet access. Read `OPENRSI_KNOWLEDGE_BASE_URL` for the shared
  eight-paper catalog and internal PDF links. Do not bundle task-specific material.
- Read `OPENRSI_TASK` for the problem instruction, writable workspace,
  candidate paths, declared models and metered gateway endpoints. Route every
  model request through those endpoints. Do not hard-code public provider URLs.
- Call `evaluate --json PATH` on candidate snapshots during research so
  intermediate progress is recorded. Retain the best candidate in the designated
  workspace for final independent verification. Text claiming a score is not evidence.
- Keep all credentials outside the source directory. The source archive is
  limited to 8 MiB; expanded submitted source also defaults to 8 MiB. Check both
  before upload with `openrsi-space remote limits ./my-harness` (no credentials
  or upload). See [source limits](source-limits.md). Source cannot contain symlinks. `.env*`, Git metadata, local
  state and virtual environments are excluded; these exclusions do not replace
  checking your own source for secrets.
- Declare models and choose spending caps and timeouts deliberately. Token
  ceilings are optional and disabled by default; tokens remain metered. The service must
  support the provider protocol and resolve reference pricing before inference.
  See [provider availability and rollout status](live-models.md#implemented-providers-and-hosted-permission).
  Arbitrary model names do not imply arbitrary provider protocols are available.

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
If it is blocked or you decline it, stop and report the blocker and untested steps.
Every new hosted submission requires the matching private bundle and a recorded local cap
at least as large as the remote cap. Actual spending may be lower. Resolve the local failure before submitting; there is no bypass.

## 4. Choose funding and start the official evaluation

Review the prepared harness and its local checks first. If a coding agent is
helping, it should report what it built, what it tested, and the proposed model
and limits, then wait for your approval to run unless you already authorized
execution once ready. You decide when the harness is ready for remote evaluation.

### Platform-funded run, when enabled

Check `openrsi-space remote funding-policy` before choosing your local model.
Choose an exact model on a funded API provider and an ended local run with
the same model (or supported provider equivalent) and reasoning settings. The service validates its price.
For this 3-credit example, the local record needs a **budget cap of at least
3 credits**; actual spending may be lower.
The CLI uploads its private evidence separately from source; it reads and sends no
personal model credential for the remote run.

Accepted remote results appear automatically on the OpenRSI dashboard. Use
`--wait` to follow verification, or resume with `remote wait EVALUATION_ID`.
For an optional Yukon submission and repository record, add
`--publish-to-yukon --benchmark BOARD_UUID --note-file submission-note.md --no-dependencies`; use
`--dependencies-file` when declaring reused submissions. This publication runs
in the CLI and is not required for dashboard visibility. Supply
`--benchmark BENCHMARK_UUID` outside a Yukon checkout. See
[optional Yukon publication](automatic-publication.md).

```sh
openrsi-space remote submit .openrsi/my-harness \
  --platform-funded --local-run /path/to/local/run.json \
  --problem-release TAG --provider PROVIDER --model EXACT_MODEL --budget 3 \
  --no-token-limit --max-seconds 10800 --wait
```

Use the current problem tag and your authorized limits. If funding is disabled or
your local record does not qualify, stop and resolve the reported reason; do not
automatically switch to personal model access or start more paid local testing.
See [funded submission details](platform-funded-inference.md).

New evaluations default to 10,800 seconds (3 hours). The current service accepts
up to 21,600 seconds (6 hours) with `--max-seconds 21600`; use a shorter limit
when appropriate. These flags override limits saved in `evaluation.json`.
New runs have no model-token ceiling by default. `--no-token-limit` clears a
saved ceiling; use `--max-tokens N` to add one. Token usage is still recorded and
spending limits remain in effect.

### Personal API-key interface (currently disabled)

Hosted evaluations use platform funding. Do not submit a personal model key or
subscription token, or switch credential modes to bypass a funding rejection.
Your Yukon login identifies your account; it is separate from local model access.

### Monitor either kind of run

The CLI prints an **evaluation ID**. Keep it:

```sh
openrsi-space remote status EVALUATION_ID
openrsi-space remote wait EVALUATION_ID
```

These commands resume retrieval of the same evaluation. Use the existing ID after
a wait or connection is interrupted. A service restart cannot resume active
research automatically. `status` reports progress; use `wait` to validate the final
result and inspect `valid` and the receipt path.

To deliberately run again, follow
[starting a new attempt](submission-recovery.md#how-do-i-start-a-new-attempt-after-a-terminal-result):
the current client retains the pending request after `status` but clears it when
`wait` processes a terminal result. Repeating `submit` can therefore either recover
the old attempt or create a new one, depending on that saved state.

## 5. Retrieve and inspect the receipt

After a successful `--wait`, OpenRSI prints the validity, score pair,
evaluation ID, private artifact paths and receipt path. Normally the receipt
is `.openrsi/my-harness/verification.json`. Use the exact printed path if
the source changed while the run was in progress.

Check that verification succeeded. Accepted results appear on the dashboard
automatically; no Yukon publication command is required. Keep the whole receipt
unchanged. Editing your local harness afterwards does not change the result
that the receipt identifies.

## 6. Optionally publish to Yukon

Only continue if you want an additional Yukon submission and repository record.
From the same workspace, the current client can publish without a Yukon clone:

```sh
openrsi-space remote wait EVALUATION_ID --publish-to-yukon \
  --benchmark BOARD_UUID --publication-title "HARNESS NAME" \
  --note-file submission-note.md --no-dependencies
openrsi-space remote publication EVALUATION_ID
```

Use the target board's benchmark UUID from the participation instructions or
Yukon benchmark metadata, not its repository name. The current dev board is
`bd33c240-a4b3-4671-ad88-84b847859293`. Keep the same API environment and account
as the remote run. This publishes the existing result without new inference.

Write `submission-note.md` before submitting. Yukon requires a public note
of 5–100 KiB. Explain the harness, knowledge/dependencies, exact model and effort,
spending/token/time caps, commands, experiments, measured results, failures and
limitations. Record cost at the best result separately from total usage.
Exclude secrets, personal data and private local paths. Do not pad with
invented experiments to meet the length requirement. The UI attributes this full
note to the solver. Its separate “About this harness” text is generated by the
platform from reviewed source when available; your note does not replace that summary.

Publish with the exact model and harness attribution for your run:

If automatic publication already reports `published`, skip this manual step.
Otherwise, the alternative manual workflow uses a pinned Yukon checkout. Install
the Yukon CLI for the same API environment, then create a separate checkout:

```sh
curl -fsSL "$YUKON_API_URL/yukon/install.sh" | sh
yukon clone bxue-l2/openrsi-space openrsi-publication
cd openrsi-publication
uv sync --frozen
yukon setup
mkdir -p submission
cp /absolute/path/to/verification.json submission/verification.json
yukon run
```

Replace the receipt path with the exact path returned by remote verification.
Use the board selected in the UI; the clone example above is for the current dev
board. Keep its receipt checker pinned. `yukon run` checks the existing receipt,
without another research run. Put the public note in this publication checkout,
then:

```sh
openrsi-space yukon-submit --note-file submission-note.md \
  --model "EXACT MODEL" --harness "HARNESS NAME" --no-dependencies
yukon submissions --all --json
```

Use your actual model and harness. If reusing an earlier Yukon submission,
replace `--no-dependencies` with `--dependencies-file dependencies.json`,
following `yukon skill`.

**Use `openrsi-space yukon-submit` for this challenge.** It invokes stock
`yukon submit` and registers the resulting execution/receipt binding with
OpenRSI. Plain `yukon submit` alone does not complete that binding.
If binding fails, repeat the same helper command to resume its saved operation;
follow its recovery message if the upload outcome is unknown.

Yukon creates a candidate commit and runs OpenRSI's GitHub Actions workflow.
The workflow authenticates to the verifier and fetches the existing verified
score and curve. No second research run occurs. **Pareto submissions are
recorded without merging solution code.** The submission ID in Yukon differs
from the remote evaluation ID.

The matrix reads official scores from Yukon. It does not trust scores in
your note or enumerate GitHub branches. The OpenRSI board is served at `/openrsi`
by Yukon's challenge UI; see [UI setup and hosting](https://github.com/Layr-Labs/yukon/blob/master/apps/challenges-ui/challenges/openrsi/README.md). You can
also inspect publication status with `yukon submissions --all --json`.

## Download or share your work

New remote submissions require public harness source, published after the run
stops and publication screening passes. Review files before submitting; private
submissions and solver unpublication are not supported. Traces are retained internally and cannot be downloaded or published.
An additional source license is optional. Without one, other participants may use your harness only under the limited participant license in the OpenRSI Terms of Service: to develop and submit their own harnesses to Eigen Labs challenges, with attribution to you.
Coding agents should leave `--source-license` unset unless you explicitly ask for a
source license. Existing third-party licenses still apply. Existing private runs stay private.
With the same Yukon account:

```sh
openrsi-space remote download EVALUATION_ID --kind harness --output harness.zip
```

This downloads the original evaluated harness source. Runtime traces and
complete evidence bundles are retained internally and are not downloadable.

To publish source from a run you kept private, or add an authorized license:

```sh
openrsi-space remote publish EVALUATION_ID --harness --confirm-source-reviewed
```

First download and review the exact harness ZIP. You are responsible for the
source, prompts and knowledge files you choose to make public and for having
permission to share them. Credential screening still applies and cannot be waived.
A license is optional; agents should add `--license` only when explicitly requested
for a grant you have authority to make. See [artifact sharing](artifact-sharing.md)
for downloads, license choices and publication of historical source.

## Challenge rules

OpenRSI evaluates **autonomous research**, not the replay of an existing answer.
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

Submitted material must be inspectable and comply with the [screening policy](cheat-filter.md).
Read any returned rejection reason and source location. A review failure or
inconclusive result is not an accusation of cheating. Keep the request or evaluation
ID when asking for help; approval does not prove originality or guarantee a valid circuit.

If a job fails, inspect its reported reason before choosing whether
to spend on another evaluation. Do not fabricate a receipt or score to bypass
a failure.

### Submission limits and retries

OpenRSI has no daily evaluation-count cap by default; funded runs still use
your daily credit allowance. Each account may have one evaluation running at a
time. Submission rate limits also apply, and operators can explicitly configure
a daily evaluation quota. Account identity comes from Yukon, so changing API
keys does not change these limits.

A 429 now identifies account concurrency, global capacity, submission rate, or an
explicit daily quota, with `limit`, `current`, and `retry_after_seconds`. Wait for
the indicated interval and rerun the same submission command using the same
`--state` directory, source and options. OpenRSI reuses its saved request ID;
do not delete pending state or generate a new ID to retry. You do not need to
repeat local testing to resume the same unchanged request.

For password-protected development previews, see [dev UI access](https://github.com/Layr-Labs/yukon/blob/master/apps/challenges-ui/challenges/openrsi/README.md#protected-development-previews).
