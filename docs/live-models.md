# Model access and funding

Hosted evaluations currently use platform-funded API access. Check
`openrsi-space remote funding-policy`, choose an advertised provider and exact model,
and submit with `--platform-funded --local-run PATH`. Do not send a personal
model credential. Matching local evidence must record a budget cap at least as large as the
requested remote budget. Actual local spending may be lower. See [platform-funded inference](platform-funded-inference.md).

Remote subscription-token submission has been removed. Subscription routes
cannot be selected for remote submission or quoting.
Remote commands no longer accept `--codex-auth-file`.
Personal API-key handoff remains implemented but is disabled on the hosted service.
Do not use an old subscription example or change provider labels to bypass this policy.

## Implemented providers and hosted permission

OpenRSI discovers provider implementations from the pinned Dungeness runtime.
Runtime availability does not grant remote permission: subscription routes are
local-only, and platform funding additionally requires an operator-funded API
provider. Pricing quotes and submissions enforce the same remote restrictions.

| Provider | Local access | Hosted access |
| --- | --- | --- |
| `openrouter` | Your API key | Platform funding when advertised |
| `openai` | Your API key | Personal API-key support retained but disabled |
| `anthropic` | Your API key | Personal API-key support retained but disabled |
| `openai-chatgpt` | Existing local Codex login, if authorized | Not supported |
| `claude-subscription` | Authorized local login access | Not supported |
| `grok-subscription` | [Authorized local Grok login](live-models.md#local-grok-subscription-testing) | Not supported |
| `minimax-subscription` | [MiniMax Coding/Token Plan key](live-models.md#local-minimax-subscription-testing) | Not supported |

Select the exact model advertised by the funded provider. The submitted harness
must construct compatible requests and tool definitions and use its assigned
gateway with placeholder credentials. The trusted gateway holds the platform key.
A successful pricing quote is not proof that the harness/provider pairing works.
Test locally first with matching provider, model and reasoning settings.

Direct xAI, Kimi Code and Moonshot routes remain retired.
Historical receipts and results remain readable; reading them does not permit a new run.

## First-time login

Yukon authentication identifies your account; it does not supply model access.
Use your Yukon login or supply `YUKON_API_TOKEN` privately in your terminal.
Never place credentials in source, submission notes or chat messages.

Local Dungeness testing uses your own authorized model access. See
[local testing](local-evaluation.md). Local `--codex-auth-file` and private
provider maps stay on your machine; they are not remote handoff options.
Subscription-backed local runs qualify for the supported equivalent OpenRouter
model with the same effort, source and problem. See the versioned
`local_evidence_models` mapping in `openrsi-space remote funding-policy`.
Subscription usage counts in normalized USD equivalent, not as cash charges.

## Submit source and obtain the receipt

```sh
uv run openrsi-space remote submit /path/to/harness \
  --platform-funded --local-run /path/to/completed-local-run \
  --provider openrouter --model openai/gpt-6-astra \
  --reasoning-effort high --budget 3 --wait
```

Choose an eligible exact model and authorized budget. The local run must match
this configuration and source. Retrieve an interrupted wait with
`openrsi-space remote wait EVALUATION_ID`; do not submit another paid run just to
retrieve its result. Publish the verified receipt using the
[Yukon submission workflow](submission-states.md#publish-a-verified-receipt).

## Optional personal API-key support

The CLI retains API-key support for separately configured deployments. It is
disabled on the hosted service. Use platform funding for official hosted runs;
never substitute personal credentials when funding or evidence checks reject a request.

## Claude subscription access

The `claude-subscription` route uses Anthropic Messages with a temporary bearer
access token. `anthropic` remains the API-key route. The real credential is mounted
only into the trusted gateway; the submitted harness receives a placeholder.

**Local testing only.** Remote subscription-token submission has been removed.
This route may be used by an authorized local Dungeness run;
it is not eligible for hosted submission or hosted pricing quotes. Personal
API-key submission is also currently disabled; hosted runs use platform funding.

### Supply access

Create a private JSON file outside the harness directory, with permissions 0600:

```json
{
  "claude-subscription": {
    "access_token": "YOUR_ACCESS_TOKEN",
    "expires_at": "ACTUAL_EXPIRY_AS_ISO_8601_WITH_TIMEZONE"
  }
}
```

Use an access token obtained through your own authorized Claude login and its
actual expiry. Do not supply a refresh token or copy an entire login file. OpenRSI
does not search for Claude credentials or refresh them on the server. Extra fields,
expired tokens and timestamps without a timezone are rejected. The gateway checks
expiry before every inference request, without falling back to an API key.

Select `claude-subscription` and the exact Claude model in the run configuration.
Pass the file using `--provider-access-file /absolute/private/access.json` to
`openrsi-space local run` only.
The client includes pinned local reference prices for every advertised evidence
equivalence, including `claude-opus-5-5`. Update the client if that entry is missing;
you do not need a custom `--pricing` file. The hosted evaluator does not issue
subscription credential quotes. Local subscription usage is measured in USD
equivalent, not cash charges; it can qualify for the corresponding funded model.

### Pair the harness and route

The harness must use Anthropic Messages at the assigned gateway base URL and send
explicit local conversation/tool history. Read the URL from the task's model
configuration; do not hard-code an external provider URL. The route supports only
the existing bounded inference operations, not OAuth refresh or account APIs.

For a harness containing unmodified Claude Code, configure its `ANTHROPIC_BASE_URL`
from that assigned URL and use `CLAUDE_CODE_OAUTH_TOKEN=testbed` as its placeholder.
Set `CLAUDE_CODE_MAX_OUTPUT_TOKENS=64000` (the gateway default maximum is
65,536 per request). Oversized explicit limits are rejected before generation,
not silently reduced. Also set `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1` so the CLI uses its supported
gateway-compatible request format. This disables experimental tool-search and
related beta schema features; it does not rewrite the client or loosen gateway
policy. Unset `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` in the child process so they do
not select another credential mechanism. Claude Code 2.1.311 passed a model-free request/stream check with this configuration.
Test your pinned version locally; account eligibility
and compatibility depend on your provider and pinned CLI version. The gateway
does not insert a Claude Code user-agent or rewrite prompts to impersonate a client.

Accounting uses the provider's reported input/output and cache usage, including
separate five-minute and one-hour cache writes where the quote prices them
differently. Missing duration counts prevent settlement; they do not become
zero-cost usage. The credit
cap is a normalized USD-equivalent reference budget, not a claim that the provider
charged cash or that a particular amount of subscription allowance remains.

### References

Checked 2026-10-27:

- [Anthropic: use the Agent SDK with your Claude plan](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan).
- [Claude Code environment variables](https://code.claude.com/docs/en/env-vars).

The provider determines account eligibility, applicable limits and terms.

### Claude Code recipe and checked versions

Keep this configuration in the harness entrypoint so local and remote source is
unchanged. Read the assigned provider, request model and base URL from the task.
Set `ANTHROPIC_BASE_URL` to that base URL **without appending `/v1/messages`**;
Claude Code appends the Messages path. Use the assigned model with `--model`
and the selected effort with `--effort high` when high was authorized.

| Route | Placeholder inside harness | Model |
| --- | --- | --- |
| Local `claude-subscription` | `CLAUDE_CODE_OAUTH_TOKEN=testbed`; unset other Anthropic auth variables | `claude-opus-5-5` |
| Funded `openrouter` | `ANTHROPIC_AUTH_TOKEN=testbed`; unset `CLAUDE_CODE_OAUTH_TOKEN` and `ANTHROPIC_API_KEY` | `anthropic/claude-opus-5.5` |

Both routes use `CLAUDE_CODE_MAX_OUTPUT_TOKENS=64000` and
`CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1`. Never put real credentials in this
entrypoint. OpenRouter's gateway route supports `/v1/messages`, including
Anthropic version/beta headers; `api: openai-completions` is its default API
label, not an exclusive list of supported operations. Provider/model selection
does not translate a client's request format.

The 64,000-token output limit above is an example, not a required minimum.
The gateway reserves for the requested maximum plus a conservative input bound.
If it reports `model_reservation_exceeds_remaining_budget` with `retryable: false`,
waiting or repeating the identical request will not help. Reduce the context or
explicit output limit, preserving enough output for the selected reasoning mode,
or save progress and stop. A wrapper that starts fresh sessions should checkpoint
notes before failures and stop when another session cannot make useful progress.

| Claude Code | Evidence | Compatibility notes |
| --- | --- | --- |
| 2.1.311 | Previous model-free request/stream check | Explicit output cap required by bounded gateway policy |
| 2.1.312 | Solver-reported local call after workarounds | Not independently live-validated by the platform |
| 2.1.314 | Reported available by solver | Not platform-tested |

Pin the CLI in the Dockerfile. Do not recursively `chown` the workspace:
`POINT_ADD_SDK.md` and `src/point_add_sdk.rs` are trusted read-only mounts for
this scaffold. Prepare ownership only for writable directories before dropping
privileges. See [executable harnesses](executable-harness.md).

Prices checked against [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing)
and the [OpenRouter catalog](https://openrouter.ai/api/v1/models) on 2026-10-30:
Opus 5.5 reference rates per million tokens are input $4, output $20, cache read
$0.20, five-minute cache write $5 and one-hour cache write $8. Retained runs keep
their recorded schedule. See [Claude Code environment variables](https://code.claude.com/docs/en/env-vars).

## Local Grok subscription testing

Use an authorized local Grok login with a Dungeness runtime that advertises
`grok-subscription`. Sign in using the official CLI:

```sh
grok login --device-auth
uv run openrsi-space local run /absolute/path/to/harness \
  --dungeness /absolute/path/to/dungeness \
  --provider grok-subscription --model grok-4.7 --reasoning-effort high \
  --budget 3 --no-token-limit --grok-auth-file \
  --pricing /absolute/path/to/dungeness/docs/examples/local-subscription-pricing-20261030.json
```

`--grok-auth-file` defaults to `~/.grok/auth.json` and is available only on
`local run`. Only the access token and actual expiry are staged for the local
gateway. Refresh tokens and account identity stay outside the run. An expired
or ambiguous login is rejected; sign in locally again. Keep login files outside
the harness. Do not paste tokens into source, prompts or command arguments.

The harness must send Chat Completions with the assigned model and gateway URL.
Configure high reasoning effort and a 500,000-token context in your client if
desired; the CLI's `--reasoning-effort` run setting does not rewrite arbitrary
client requests. A context window is separate from the run's total token limit.
Test tool calls, title helpers and compaction as well as the main model call.
The gateway does not impersonate the official CLI or add its identity headers.

The $3 cap measures normalized reference usage, not cash or remaining Grok plan
allowance. In-flight calls can overshoot the cap. The supplied frozen schedule
includes Grok's higher pricing tier above 200,000 input tokens.

Remote runs remain platform-funded through OpenRouter. This local route does
not enable remote subscription-token submission or change evidence eligibility.
Direct `xai` API access remains retired; use OpenRouter for funded remote access.

See [Grok's headless documentation](https://docs.x.ai/build/overview).

## Local MiniMax subscription testing

Use your MiniMax Coding/Token Plan key with `minimax-subscription`, the exact
supported model (`MiniMax-M3.1-Flash` or `MiniMax-M3`), and Chat Completions through
the assigned gateway. A subscription key and a pay-as-you-go API key may have
similar interfaces; select the plan key to consume your subscription.

Supply it privately through a local environment variable or a 0600 credential
map outside the harness. Never put the key in source or command arguments.

```sh
uv run openrsi-space local run /absolute/path/to/harness \
  --dungeness /absolute/path/to/dungeness \
  --provider minimax-subscription --model MiniMax-M3.1-Flash \
  --budget 3 --provider-token-env MINIMAX_PLAN_KEY \
  --pricing /absolute/path/to/dungeness/docs/examples/local-subscription-pricing-20261030.json
```

Set `MINIMAX_PLAN_KEY` privately before running. The harness receives only a
placeholder; the gateway substitutes the key and records provider-reported usage.
Preserve the assistant's reasoning content and tool calls in conversation history,
as required by the [MiniMax API](https://platform.minimax.io/docs/api-reference/text-openai-api).

Credits use a frozen reference schedule, not an assertion of cash billing or
remaining subscription allowance. Remote credential submission remains disabled;
this route does not change funded remote evaluation or evidence eligibility.
Live account compatibility must be checked separately from synthetic tests.
