# Quickstart

**Use your ChatGPT/Codex or Claude subscription locally; no OpenRouter key is
required.** Eigen Labs pays for the model access used in funded remote verification.
Yukon authentication identifies you; it is separate from local model access.

**Using a coding agent?** Give it [For agents](agent-prompt.md), your research idea,
preferred subscription/model and a local testing budget. It will check your setup,
build the harness, test it, and report readiness for remote verification. Expect
short progress updates and one concrete action at a time when your help is needed.
Keep credentials out of chat. You can build and test before signing in to Yukon.
The agent should begin with [Local setup](local-setup-and-testing.md), which provides the
environment checks and selected-provider preparation path.

<a id="use-the-current-submission-client-with-a-pinned-yukon-board"></a>

## Install the current submission CLI

These commands preserve an existing installation. Before a new run, follow the
[update check](client-runtime-versions.md#check-for-updates) and ask before upgrading
an existing client unless the human already authorized it.

```sh
export PATH="$(uv tool dir --bin):$PATH"
hash -r
if ! command -v openrsi-space >/dev/null 2>&1; then
  uv tool install --force --refresh "git+https://github.com/Layr-Labs/openrsi-space.git@main"
fi
```

Use the installed command directly, not an old checkout's `uv run`. It fetches its
tested Dungeness runtime. You do not need `yukon clone` for the automatic dashboard;
keep any optional Yukon receipt-checking checkout pinned.

## 1. Build your agent

```sh
openrsi-space harness create my-agent --title "My Research Agent" --output ./my-harness
```

Implement the research loop using [Build a harness](executable-harness.md).
The starter makes no model calls and cannot earn a score. Submit general-purpose
agent machinery; the assigned task supplies problem resources and the scaffold.

## 2. Choose local access and test

Follow [Local setup and testing](local-setup-and-testing.md) for machine checks, the chosen
subscription/API recipe, active problem discovery and a budgeted run. No Yukon
login is needed yet. Keep the complete run directory and its `run.json` path.
Use the reported release as `TAG` below and the policy's supported model pair.

## 3. Submit for remote verification

Use the production Yukon account and verifier below. Development credentials
do not authenticate to production.

```sh
export YUKON_API_URL=https://api.yukon.org
export OPENRSI_EVALUATOR_URL=https://verify.openrsi.space
openrsi-space remote funding
```

This checks existing credentials and available allowance without starting a run.
If it succeeds, continue; no new key or agent restart is needed. If it reports a
network/service failure, diagnose that instead of replacing credentials.

### Yukon authentication, when needed

Only if authentication is missing or rejected, open [API Keys](https://www.yukon.org/api-keys)
on the production Yukon website and create a key for this account. Use development
keys only with the matching development service.
Paste the key into this **hidden prompt in your private Bash terminal**—that is
allowed. Do not put it in chat, harness files or visible command arguments.

```bash
set +x
printf 'Yukon API key: ' && IFS= read -r -s YUKON_API_TOKEN && printf '\n' && export YUKON_API_TOKEN
openrsi-space remote funding
```

The export authenticates this shell and its children; it does not save a login or
authenticate an already-running desktop agent. Either launch your terminal-based
agent from this shell, or execute the agent's authenticated commands here yourself
and return only the evaluation ID, status and file paths. Keep using this shell
for authenticated commands, then `unset YUKON_API_TOKEN` when finished. Do not
assume a browser/device login works with OpenRSI merely because Yukon accepts it.

### Submit the matching local run

Review your source for public release and authorize the remote run. Keep source,
problem and reasoning settings unchanged. The recorded local cap must cover the
remote cap: local cap $2 and actual spend $1.73 qualifies for remote $2.
There is no minimum-spend percentage. Matching evidence and accounting checks still apply.
Every remote run, including unsuccessful runs, is listed publicly under your
username. Harness source is published after screening; the local evidence bundle
is uploaded privately and reviewed by a third-party LLM.

```sh
openrsi-space remote funding &&
openrsi-space remote submit ./my-harness \
  --problem-release TAG --platform-funded --local-run /path/to/local/run.json \
  --provider openrouter --model openai/gpt-6-astra --reasoning-effort high \
  --budget 1 --wait
```

For local Claude Opus 5.5 evidence, use remote model `anthropic/claude-opus-5.5`. Local
subscription providers change to `openrouter` only for the funded remote route;
**do not supply an OpenRouter key or local login flags to this command.**
The default allowance is $20 in model credits per account over 24 hours, cannot
be banked, and has a $1 minimum run cap. Check live policy and account allowance.

## 4. Follow, compare and improve

Reconnect after monitoring is interrupted:

```sh
openrsi-space remote wait EVALUATION_ID
```

Only if you want to stop execution, run `openrsi-space remote cancel EVALUATION_ID`
and check status until terminal. Closing monitoring alone does not stop spending.

`wait` reconnects to the existing run; it does not restart research. You can cancel,
but cannot extend an active run's budget. Accepted verified results appear on the
dashboard automatically. Each line shows one run's best verified score so far
against cumulative model credits (USD equivalent). Select a run to see individual
candidate evaluations, including ties and worse scores, at the credits used when
the agent requested evaluation. Lower ECDSA scores are better. Compare runs at the
same spending level to see which harness makes more progress.
Yukon publication is [optional](artifact-sharing.md) and uses the
existing receipt, with no new inference.

If anything fails, use [Troubleshooting](submission-recovery.md) before spending again.
For upload limits and detailed eligibility, consult the
[funding reference](funding-and-scoring.md) and
[source limits](source-and-build-rules.md). An additional source license is
optional; do not select one unless you want one. Existing third-party licenses apply.

<a id="6-optionally-publish-to-yukon"></a>
<a id="6-publish-to-yukon"></a>

## Optional Yukon publication

See [publication and recovery](artifact-sharing.md#optional-yukon-publication). This uses the existing receipt and does not start research.

## Check journey progress

After setup or a run transition, ask for a read-only status card:

```bash
openrsi-space journey list
openrsi-space journey status --harness HARNESS_ID
openrsi-space journey status --local-run LOCAL_RUN_PATH --json
openrsi-space --state .openrsi journey status --evaluation EVALUATION_ID --json
```

JSON includes the rendered `card` for your agent to display in chat. Run the
command from the original workspace (or use its original `--state` directory).
The station groups recorded runs into harness cards. With multiple records,
`journey status` shows the overview; choose a harness or run explicitly. Lists
use saved status, not live server queries. Only a selected remote run is refreshed.
All run IDs are retained in JSON; an expanded card shows up to five runs.
This collection covers the selected workspace, not every machine or account. Remote checks use your existing login and configured evaluator.
It never starts, retries or publishes a run. Missing data is unknown, not zero;
saved local status does not prove a process is still running. Execution, final
verification and the local evidence precheck are separate observations. A passed
precheck does not guarantee that a particular remote request is eligible.

Before a run exists, discuss your idea and preparation with the agent; the CLI
cannot infer those human decisions. Use `remote wait` for an ongoing remote run,
rather than adding another polling loop.
