# Claude subscription access

The `claude-subscription` route uses Anthropic Messages with a temporary bearer
access token. `anthropic` remains the API-key route. The real credential is mounted
only into the trusted gateway; the submitted harness receives a placeholder.

**Status:** implemented and tested against synthetic upstream responses. Hosted
rollout and an authorized live Claude inference check are pending. Older hosted
runtimes will correctly report this provider as unavailable.

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
actual expiry. Do not supply a refresh token or copy an entire login file. Catalyst
does not search for Claude credentials or refresh them on the server. Extra fields,
expired tokens and timestamps without a timezone are rejected. The gateway checks
expiry before every inference request, without falling back to an API key.

Select `claude-subscription` and the exact Claude model in the run configuration.
Pass the file using `--provider-access-file /absolute/private/access.json` to
`catalyst local run`, `catalyst remote submit`, or `catalyst remote renew`.
For local testing, supply a pricing snapshot with `--pricing`; it must contain a
`claude-subscription` entry for the selected model. Hosted submission obtains an
immutable quote from the evaluator. Existing pricing snapshots are unchanged.

## Pair the harness and route

The harness must use Anthropic Messages at the assigned gateway base URL and send
explicit local conversation/tool history. Read the URL from the task's model
configuration; do not hard-code an external provider URL. The route supports only
the existing bounded inference operations, not OAuth refresh or account APIs.

For a harness containing unmodified Claude Code, configure its `ANTHROPIC_BASE_URL`
from that assigned URL and use `CLAUDE_CODE_OAUTH_TOKEN=testbed` as its placeholder.
Set `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1` so the CLI uses its supported
gateway-compatible request format. This disables experimental tool-search and
related beta schema features; it does not rewrite the client or loosen gateway
policy. Unset `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` in the child process so they do
not select another credential mechanism. Claude Code 2.1.311 passed a model-free request/stream check with this configuration.
Test your pinned version locally before remote submission; live account eligibility
and inference have not yet been validated. The gateway
does not insert a Claude Code user-agent or rewrite prompts to impersonate a client.

Accounting uses the provider's reported input/output and cache usage. The credit
cap is a normalized USD-equivalent reference budget, not a claim that the provider
charged cash or that a particular amount of subscription allowance remains.

## References

Checked 2026-10-27:

- [Anthropic: use the Agent SDK with your Claude plan](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan).
- [Claude Code environment variables](https://code.claude.com/docs/en/env-vars).

The provider determines account eligibility, applicable limits and terms.
