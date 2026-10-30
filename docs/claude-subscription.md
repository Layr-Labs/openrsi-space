# Claude subscription access

The `claude-subscription` route uses Anthropic Messages with a temporary bearer
access token. `anthropic` remains the API-key route. The real credential is mounted
only into the trusted gateway; the submitted harness receives a placeholder.

**Local testing only.** Remote subscription-token submission and renewal have
been removed. This route may be used by an authorized local Dungeness run;
it is not eligible for hosted submission or hosted pricing quotes. Personal
API-key submission is also currently disabled; hosted runs use platform funding.

## Supply access

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

## Pair the harness and route

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

## References

Checked 2026-10-27:

- [Anthropic: use the Agent SDK with your Claude plan](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan).
- [Claude Code environment variables](https://code.claude.com/docs/en/env-vars).

The provider determines account eligibility, applicable limits and terms.

## Claude Code recipe and checked versions

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
