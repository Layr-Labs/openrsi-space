# Local setup and testing

Follow this sequence and only your chosen provider branch. Local testing needs
neither a Yukon key nor a separate Dungeness clone or server.

## 1. Confirm the plan and inspect the machine

Confirm the research idea, selected model access and authorized total test budget.
Reuse existing choices. Tell the human setup is underway and no calls have started.

Run these checks without dumping the environment or credential files:

```sh
uname -s
uname -m
git --version
uv --version
docker version
docker info --format 'CPUs={{.NCPU}} MemoryBytes={{.MemTotal}} Architecture={{.Architecture}}'
df -h .
```

| Finding | Next action |
| --- | --- |
| Git or uv missing | Install the missing tool using the supported OS procedure; uv can supply Python 3.11+. |
| Docker missing | Use [Docker's installation instructions](https://docs.docker.com/get-started/get-docker/) for this OS. |
| Docker client works but server is unavailable | Start Docker Desktop or the Docker service, then repeat `docker version`. |
| Docker permission denied | Explain the required host permission change; do not repeatedly retry or run the entire workflow as root. |
| Insufficient disk or Docker resources | Report available resources and the selected problem's requirements. Do not delete unrelated images or files automatically. |
| Unsupported host/tool combination | Report the specific blocker and a supported environment; do not guess that a different architecture is compatible. |

Docker Desktop resources refer to its VM, not the host totals. Requirements depend
on the selected problem. Give one exact action if human intervention is needed.
Host tool installations are not inherited by the harness image.

## 2. Install the current client and discover the task

This guide uses the **production repository and service**. If the human supplied
an official development environment, use its matching repository and evaluator;
do not mix development and production credentials.

```sh
uv tool install --force --refresh "git+https://github.com/Layr-Labs/openrsi-space.git@main"
export PATH="$(uv tool dir --bin):$PATH"
hash -r
openrsi-space --version
mkdir -p openrsi-workspace
cd openrsi-workspace
export OPENRSI_EVALUATOR_URL=https://verify.openrsi.space
openrsi-space problem current
openrsi-space remote funding-policy
```

Continue once discovery succeeds and policy advertises the chosen model pair.
Record the installation commit (not just `--version`), problem tag/digest and
model/reasoning. Use the installed CLI, not an older checkout's `uv run`.
The CLI fetches its tested Dungeness runtime during preparation. Discovery errors
are not a reason to request a Yukon key or discard existing records.

## 3. Prepare only the selected local access route

Start with your existing subscription. A separately billed API is optional; do
not switch to one without the solver's authorization.

| Your access | Harness client | Local provider | Credential option |
| --- | --- | --- | --- |
| ChatGPT subscription | Codex / Responses | `openai-chatgpt` | `--codex-auth-file` |
| Claude subscription | Claude Code / Messages | `claude-subscription` | `--provider-access-file` |

No personal OpenRouter key is needed for these local routes. A subscription is
not a universal API credential: use its matching client and the setup below.
Eigen Labs funds remote OpenRouter access using the supported model equivalent;
see [funding eligibility](funding-and-scoring.md#local-access-and-remote-eligibility).

### ChatGPT subscription with a Codex harness

```sh
codex login status
```

If Codex is missing, install its official CLI for the host. If signed out, run
`codex login` and let the human complete ChatGPT sign-in; on a headless machine,
use `codex login --device-auth`. Do not ask for an OpenRouter key.

OpenRSI needs a file-based login. With authorization, check whether the selected
Codex home contains `auth.json` without displaying it. A desktop/keychain login
alone is not enough. If file storage is permitted, the explicit setup is:

```sh
codex -c 'cli_auth_credentials_store="file"' login
```

**Ready when:** the authorized file-based login is available and the harness uses
Codex with the assigned Responses gateway. Use local provider `openai-chatgpt`
and `--codex-auth-file`; its default path is `~/.codex/auth.json`. For a custom
`CODEX_HOME`, pass its absolute auth-file path explicitly. Never print or upload it.

### Claude subscription with a Claude Code harness

```sh
claude auth status
```

If Claude Code is missing, install its official CLI. If signed out, run
`claude auth login` and let the human complete subscription sign-in.

Then execute the existing
[private access-map helper](model-access.md#prepare-access-from-a-local-claude-code-login)
with authorization. This is a required setup step, not something the human must
design: for the supported Linux file-based login it copies only the access token
and expiry into a private map, without displaying credentials or copying refresh
tokens. It does not apply to other credential-store formats; report those explicitly
instead of inventing an expiry or exporting browser credentials.

**Ready when:** the private map exists and the harness uses Claude Code with the
assigned Messages gateway. Use local provider `claude-subscription` and
`--provider-access-file "$HOME/.config/openrsi-space/claude-local-access.json"`.
An existing Claude login is not imported automatically. Remove the temporary map
after testing, preserving the original login.

### API access explicitly selected by the human

Use the [supported provider table](model-access.md#implemented-providers-and-hosted-permission)
and its recipe. Confirm the harness supports that API protocol and the local model
has an eligible remote equivalent. Supply the key through the documented private
input, such as `--provider-token-env MODEL_API_KEY`; never put its value in a command
argument, source or chat. Local OpenRouter uses the human's account, not platform
funding, and needs the [inference-only configuration](runtime-reference.md).

## 4. Prepare the harness without inference

Follow [Build a harness](executable-harness.md); inspect an existing manifest and
Dockerfile before changing them. Install agent/dependency/document tools in the
image, honor assigned task paths and read-only files, and implement error recovery.

Choose one route above. Replace `HARNESS_DIR`, `TAG`, `LOCAL_PROVIDER`, `LOCAL_MODEL`,
`EFFORT` and `LOCAL_CAP` with the inspected configuration and authorized cap:

```sh
openrsi-space remote limits HARNESS_DIR
openrsi-space local run HARNESS_DIR --problem-release TAG \
  --provider LOCAL_PROVIDER --model LOCAL_MODEL --reasoning-effort EFFORT \
  --budget LOCAL_CAP --prepare-only
```

**Ready when:** source packaging and preparation succeed. This builds/prepares
without reading model credentials or making model calls. It does not prove the
agent can run successfully. Fix concrete build/configuration errors and repeat
this inexpensive check; do not change evidence from an earlier run.

## 5. Start the authorized local test

Announce **Testing locally**, the selected model and the cap. Run the same local
command without `--prepare-only`, adding **one** credential option from step 3.
Use the remaining authorized budget across attempts. Subscription usage consumes
plan allowance and is measured in normalized model credits, not a cash purchase.

Report meaningful changes in candidate evaluations, usage and errors. Keep the
complete run directory and reported `run.json` path. Separate agent execution,
candidate verification and evidence completeness; wrapper exit success alone is
not enough. A valid local circuit is not required for evidence eligibility.

Return:

```text
Stage: preparing | testing locally | ready for remote verification | blocked
Setup: tools, provider/model/reasoning, problem release
Local outcome: execution / candidate verification / evidence completeness
Budget: recorded cap / actual usage / remaining authorized testing allowance
Records: local run path
Next action: what the agent will do, or one action needed from the human
```

If blocked, use [Troubleshooting](submission-recovery.md) and identify whether the
evidence points to the harness, platform, account/provider, or an unknown cause.
Do not automatically restart paid research. When ready, continue at
[remote submission](solver-guide.md#3-submit-for-remote-verification), including
authentication, allowance, private evidence review and public-source consent.

## Local outcomes and diagnostics

Inspect these independently; wrapper completion is not research success:

| Retained field | Meaning |
| --- | --- |
| `runtime_exit_code`, `runtime_record_status` | Harbor/runtime completion, before nested failures are checked. |
| `agent_exit_code`, `agent_reported_outcome` | Harness exit and recognized client outcomes, including the last session's reason/HTTP status. A recovered session error is not automatically a failed run. |
| `candidate_evaluations`, `metrics` | Trusted intermediate validity, best score and evaluation count when retained; never inferred from stdout. |
| `final_verification` | Retained trusted `score.json`, separate from intermediate candidates. Invalid penalties are not valid scores; missing files are `not_retained`. |
| `local_evidence_precheck_passed`, `local_evidence_precheck` | Ended execution with complete settled exchanges. This is preliminary eligibility, not hosted acceptance or execution success. Matching and recorded-cap checks still apply. |

Failed/cancelled runs can supply evidence; zero-call runs cannot. No valid local
circuit is required. Inspect retained files without running inference again.

During execution, the CLI prints request/spending progress every 15 seconds from
`usage/summary.json`; Harbor stdout may arrive only at completion. The final
summary points to exception/output files without echoing secrets. `run-status`
uses the agent deadline, excluding build/startup time.

`problem_identity.release_manifest_sha256` matches `problem current`;
`problem_identity.assembled_package_sha256` identifies the generated package
(the older `problem.version`). These hashes need not match; never edit them.
