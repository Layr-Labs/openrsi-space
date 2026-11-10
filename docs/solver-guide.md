# Quickstart

**Use your ChatGPT/Codex or Claude subscription locally; no OpenRouter key is
required.** Eigen Labs pays for the model access used in funded remote verification.
Yukon authentication identifies you; it is separate from local model access.

**Using a coding agent?** Give it [For agents](agent-prompt.md), your research idea,
preferred subscription/model and a local testing budget. It will check your setup,
build the harness, test it, and report readiness for remote verification. Expect
short progress updates and one concrete action at a time when your help is needed.
Keep credentials out of chat. You can build and test before signing in to Yukon.
The agent should begin with [Local setup](local-evaluation.md), which provides the
environment checks and selected-provider preparation path.

<a id="use-the-current-submission-client-with-a-pinned-yukon-board"></a>

## Install the current submission CLI

```sh
uv tool install --force --refresh "git+https://github.com/Layr-Labs/openrsi-space.git@main"
export PATH="$(uv tool dir --bin):$PATH"
hash -r
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

Follow [Local setup and testing](local-evaluation.md) for machine checks, the chosen
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
dashboard automatically. Each line in the run-history chart represents one run.
Each dot marks a candidate evaluation: its score and cumulative model credits
(USD equivalent) used when the agent requested evaluation. Lower ECDSA scores are
better. Compare runs at the same spending level to see which harness makes more progress.
Yukon publication is [optional](artifact-sharing.md) and uses the
existing receipt, with no new inference.

If anything fails, use [Troubleshooting](submission-recovery.md) before spending again.
For upload limits and detailed eligibility, consult the
[funding reference](platform-funded-inference.md) and
[source limits](source-limits.md). An additional source license is
optional; do not select one unless you want one. Existing third-party licenses apply.

<a id="6-optionally-publish-to-yukon"></a>
<a id="6-publish-to-yukon"></a>

## Optional Yukon publication

See [publication and recovery](artifact-sharing.md#optional-yukon-publication). This uses the existing receipt and does not start research.
