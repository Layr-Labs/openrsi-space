# Local model access reference

Start with [Local setup](local-evaluation.md) and read only your selected provider section. Funded remote policy lives in [Funding and scoring](platform-funded-inference.md).

<a id="implemented-providers-and-hosted-permission"></a>

## Choose local model access

**Start with your existing model subscription.** ChatGPT/Codex and Claude Code
can use their authorized local logins; no personal OpenRouter key is needed.
Testing consumes the plan's allowance. API access is an optional alternative with
separate provider charges; do not switch to it without the solver's authorization.

| Local access | Provider | Setup |
| --- | --- | --- |
| ChatGPT subscription with Codex | `openai-chatgpt` | [Existing Codex login](#local-chatgpt-subscription-setup) |
| Claude subscription with Claude Code | `claude-subscription` | [Existing Claude login](#claude-subscription-access) |
| Optional, separately billed API access | `openrouter`, `openai`, `anthropic` | Your authorized provider API key |

## Funded remote verification

Subscription local runs **can qualify** for the supported equivalent remote model.
Check `openrsi-space remote funding-policy` before testing; source, problem and
reasoning settings must also match. Local provider labels may differ from remote
labels. Not every locally supported model has an eligible remote equivalent.

Eigen Labs supplies and pays for remote OpenRouter access. Submit with
`--platform-funded` and the exact supported remote model; do not upload a personal
API key or subscription login. Subscription credentials are used locally only—this
does not mean their local evidence is ineligible. See [funding and evidence rules](platform-funded-inference.md).

The pinned Dungeness runtime defines available providers. The unchanged harness
must support its assigned API protocol, endpoints and placeholder credentials on
both routes; selecting a model does not translate requests. Test that pairing
locally. A successful pricing quote alone does not establish compatibility.

Direct xAI, Kimi Code and Moonshot routes remain retired.
Historical receipts and results remain readable; reading them does not permit a new run.

## Local ChatGPT subscription setup

Use a compatible Codex harness and the `openai-chatgpt` local provider. Run
`codex login status` to check the active authentication method without printing
the login file. If needed, run `codex login` and select ChatGPT sign-in.
For a headless machine, `codex login --device-auth` is the documented alternative.

OpenRSI reads a file-based Codex login. If your existing login is in an OS
keychain, and your local policy permits file storage, establish a file-based
login explicitly:

```sh
codex -c 'cli_auth_credentials_store="file"' login
```

Use the resulting local `auth.json` with `openrsi-space local run ...
--provider openai-chatgpt --codex-auth-file`. The default path is
`~/.codex/auth.json`; for another `CODEX_HOME`, pass its absolute auth-file path.
Do not print, commit or upload that file. If a managed policy prevents this
storage method, report that integration limitation; do not bypass the policy.
The official [Codex authentication guide](https://developers.openai.com/codex/auth)
describes login methods and credential storage. The
[local guide](local-evaluation.md) covers setup and the budgeted run command.

## Claude subscription access

The `claude-subscription` route uses Anthropic Messages with a temporary bearer
access token. `anthropic` remains the API-key route. The real credential is mounted
only into the trusted gateway; the submitted harness receives a placeholder.

**The `claude-subscription` provider is local-only; its run records can qualify
for the advertised equivalent funded remote model.** For remote submission,
select `openrouter` and its mapped model ID with platform funding. Do not send
subscription credentials to the hosted service or quote a remote subscription
provider. Personal API-key submission is also currently disabled.

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

### Prepare access from a local Claude Code login

OpenRSI currently takes an explicit private access map for this route; being
signed into Claude Code alone does not supply the CLI flag. For a Linux
file-based Claude Code login containing `claudeAiOauth.accessToken` and
`claudeAiOauth.expiresAt` (Unix milliseconds), the following helper converts only
those fields. Run it on the solver's machine with permission. It never prints
credentials, copies refresh tokens, contacts a provider or starts inference.

```sh
python3 - <<'PY'
import json
import os
from pathlib import Path
from datetime import datetime, timezone

source = Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))) / ".credentials.json"
destination = Path.home() / ".config/openrsi-space/claude-local-access.json"
try:
    with source.open() as handle:
        login = json.load(handle)["claudeAiOauth"]
    token, millis = login["accessToken"], login["expiresAt"]
    if not isinstance(token, str) or not token or type(millis) is not int:
        raise ValueError("Unsupported local login format")
    expiry = datetime.fromtimestamp(millis / 1000, timezone.utc)
    if expiry <= datetime.now(timezone.utc):
        raise ValueError("Local login expired")
except (OSError, KeyError, TypeError, ValueError, OverflowError):
    raise SystemExit("Cannot import this local login. Check Claude sign-in or the credential-store format; no API key is required.")

destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
try:
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    raise SystemExit("Private access map already exists. Remove that temporary map before refreshing it; preserve your original Claude login.")
with os.fdopen(fd, "w") as out:
    json.dump({"claude-subscription": {"access_token": token, "expires_at": expiry.isoformat()}}, out)
    out.write("\n")
print("Created private Claude local access map; no credentials displayed.")
PY
```

Pass the resulting path with `--provider-access-file`, as shown in the
[subscription quickstart](local-evaluation.md#3-prepare-only-the-selected-local-access-route).
Remove this temporary access map after local testing. Keep the original Claude
login unchanged. If login is stored in an OS keychain or uses another format,
this helper does not apply: use an authorized local credential method to create
the same two-field map, or report the unsupported storage method. Do not guess
an expiry, export a browser session, paste credentials into chat, or request an
OpenRouter key as a substitute.

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
