# Catalyst: guide for solvers

Build an autonomous research harness that finds better **ecdsa.fail** quantum
circuits. Catalyst runs your source remotely in Dungeness, meters model use,
and independently verifies the candidates. Yukon publishes the verified results.

## Before you participate: your account, your model usage

**You provide your own model credentials. Catalyst runs your agent on our
remote server using access to your model account. Model calls consume your API
credits or subscription allowance; Catalyst does not provide free model access.**

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

The service keeps supplied model access temporarily in memory/tmpfs for execution
and removes it afterward. It does not retain it in results or artifacts.
Refresh credentials remain on your machine. A coding agent must obtain your
authorization for this remote credential use and the spending cap before launching
a run; installing the tools or finding an existing login does not grant it.

## Participation flow

**The flow:** build your autonomous agent → optionally test locally → review
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
usage and rejects an over-cap result. See [accounting details](tier-accounting.md).

## 1. Install and connect

You need Git, [uv](https://docs.astral.sh/uv/getting-started/installation/),
Python 3.11 or newer (uv can install Python), and a current Yukon CLI.
Docker and Dungeness run on the service; you do not need them just to submit.
Local Docker smoke tests are optional. For full local research runs, anyone can
clone the public [Dungeness repository](https://github.com/Layr-Labs/dungeness).
See [local testing options](local-evaluation.md).
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

Your package can contain source, prompts, a raw-paper knowledge base, helper
programs, configuration and a Dockerfile with pinned dependencies. You can
use your own agent architecture, subprocesses or search framework.

To generate an editable starter:

```sh
uv run catalyst harness create my-agent --output .catalyst/my-harness
```

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
  --provider kimi-code --model k3 --budget 3 \
  --max-tokens 1000000 --max-seconds 900 \
  --prompt-model-token --wait
```

**That command starts an evaluation.** Run it only when your source and
chosen spending cap are ready. The entrypoint must match your Dockerfile.
Do not combine `--entrypoint` with an existing `harness.json`.

Runtime requirements:

- Install dependencies and include knowledge files in the image. The research
  container has no public internet access.
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
- Declare models and choose token/time caps deliberately. The service must
  support the provider protocol and resolve reference pricing before inference.
  The current VM enables `kimi-code` and `openai-chatgpt`; arbitrary model names
  do not imply arbitrary provider protocols are available.

See [the generic harness contract](generic-harnesses.md) for model ensembles,
packaging, pricing and gateway details.

## 3. Supply model access and evaluate

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

For the copied EvoX example, obtain a **Kimi Code membership key** from the
[Kimi Code console](https://www.kimi.com/code/console). Then run:

```sh
uv run catalyst remote submit .catalyst/my-harness \
  --provider kimi-code --model k3 --budget 3 \
  --max-tokens 1000000 --max-seconds 900 \
  --prompt-model-token --wait
```

Enter the model key at the hidden prompt. A Moonshot platform key belongs
to a different provider and is not a Kimi Code membership key.
The $3 cap is an example, not a required challenge budget or spending target.

For a Codex/ChatGPT harness instead:

```sh
uv run catalyst remote submit .catalyst/my-harness \
  --provider openai-chatgpt --model gpt-6-astra \
  --reasoning-effort high --budget 3 \
  --max-tokens 1000000 --max-seconds 900 \
  --codex-auth-file --wait
```

`--codex-auth-file` reads an existing local `~/.codex/auth.json` and sends its
temporary access material to the remote service; it is not local-only.
No manual token extraction is needed. You can supply an explicit path. See
[model login setup](live-models.md#first-time-login) if the file is absent.
The current generic gateway's live compatibility with this updated Codex
example still needs revalidation; the deployed EvoX/Kimi path has completed
the hosted end-to-end flow.

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

## 4. Retrieve and inspect the receipt

After a successful `--wait`, Catalyst prints the validity, score pair,
evaluation ID, private artifact paths and receipt path. Normally the receipt
is `.catalyst/my-harness/verification.json`. Use the exact printed path if
the source changed while the run was in progress.

Continue only with a valid verified result:

```sh
cp .catalyst/my-harness/verification.json verification.json
yukon run
```

Copy the **whole receipt unchanged**. Do not extract a token field, edit a
score, or copy another solver's receipt. Catalyst checks the stored evaluation's
owner, problem and source identity. Editing your local harness afterwards
does not change what this receipt refers to.

`yukon run` retrieves the existing result; it does not build or execute the
harness again. A local claimed score cannot substitute for a verified receipt.

## 5. Publish to Yukon

Write `submission-note.md` before submitting. Yukon requires a public note
of 5–100 KiB. Explain the harness, knowledge/dependencies, exact model and effort,
spending/token/time caps, commands, experiments, measured results, failures and
limitations. Record cost at the best result separately from total usage.
Exclude secrets, personal data and private local paths. Do not pad with
invented experiments to meet the length requirement.

For the EvoX/Kimi example:

```sh
uv run catalyst yukon-submit --note-file submission-note.md \
  --model "Kimi K3" --harness "SkyDiscover/EvoX" --no-dependencies
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

Your harness and recorded traces are private by default, even after publishing
the score to Yukon. With the same Yukon account:

```sh
uv run catalyst remote download EVALUATION_ID --kind complete --output complete.zip
```

This includes submitted source and retained, sanitized run evidence. It does
not include container images, dependency caches or every arbitrary workspace
file. Read `coverage.json` inside the archive for exclusions.

To make your own source public:

```sh
uv run catalyst remote publish EVALUATION_ID --harness --license MIT --confirm-source-reviewed
```

First download and review the exact harness ZIP. You are responsible for the
source, prompts and knowledge files you choose to make public and for having
permission to share them. Credential screening still applies and cannot be waived.
Choose a license you have authority to grant. Trace publication is a separate
choice after downloading and reviewing the sanitized traces:

```sh
uv run catalyst remote publish EVALUATION_ID --traces --confirm-traces-reviewed
```

Traces can reveal code and research content. See [artifact sharing](artifact-sharing.md)
for downloads, license choices and unpublishing.

## Challenge rules

Catalyst evaluates **autonomous research**, not the replay of an existing answer.
Harnesses that fetch, search for, bundle, or reproduce existing ECDSA GitHub or
leaderboard solutions are prohibited and are rejected when detected. This
includes asking the agent to recall a memorized submission, embedding it in
prompts or knowledge files, and disguising it as an answer cache or dependency.
Removing attribution, changing formatting, or disabling internet access does
not make reuse permitted.

Use the pinned task and starting baseline. Ordinary framework dependencies,
papers, citations, general algorithmic knowledge and the provided baseline are allowed.
Do not access host resources, tamper with the verifier or bypass metering.
Candidate source must satisfy the pinned verifier and screening rules.

The published-solution screen refreshes the official repository's branches and
open/closed pull-request heads before a remote run. Substantial matching source
outside the pinned baseline blocks the run before build or model usage. The
rejection reason and private `solution-corpus.json` report identify the harness
location and reference blob. A failed refresh blocks screening without declaring
cheating. The optional LLM source reviewer is not yet enabled on the service.
Neither check proves originality or detects all memorization. See
[the screening policy and deployment status](cheat-filter.md).

If a job fails, inspect its reason and private traces before choosing whether
to spend on another evaluation. Do not fabricate a receipt or score to bypass
a failure.
