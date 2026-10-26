# Temporary model access

Catalyst is a benchmark for research agent harnesses. You submit your own
harness, using your own model account, to run in a controlled environment on
Catalyst's servers so that its performance can be independently verified and
compared with others on a public leaderboard.

Catalyst receives temporary model access for the run you start. When you use a
supported login handoff, your refresh credentials stay on your device. Supplied
access tokens are discarded during run cleanup. If you use an API key, Catalyst
uses it only for the run you start and removes it during cleanup.

You are responsible for ensuring your use complies with your model provider's
terms.

Review the provider, exact model and spending cap before starting a run. Supplying
model access to `catalyst remote submit` authorizes its use for that run on
Catalyst's servers. Your Yukon key identifies you and does not pay for model calls.
Keep model credentials out of harness source. Use the credential options below for the selected provider.

For the full human walkthrough, start with [the solver guide](solver-guide.md).
Coding agents should read [the agent instructions](agent-prompt.md).

## Implemented providers and hosted permission

Catalyst discovers provider IDs from the selected, pinned Dungeness runtime using
`dungeness providers`. The gateway registry is authoritative: Catalyst has no
separate provider allowlist and does not install provider profiles into Dungeness.
Pricing quotes and submissions use the same runtime-derived provider check.

The current Dungeness registry implements:

| Provider | Model access | Harness protocol |
| --- | --- | --- |
| `anthropic` | API key | Anthropic Messages |
| `openai` | API key | OpenAI API routes supported by the gateway |
| `openai-chatgpt` | Temporary Codex login handoff | Responses |
| `openrouter` | API key; requires operator-enabled inference-only routing | Supported gateway routes |

Runtime support is necessary but does not establish usable model credentials,
exact model pricing or harness API compatibility. A quote validates provider
availability and reference pricing; it does not make an inference call or prove
that a complete evaluation will succeed. The service still controls whether
model access is enabled and enforces run limits.

Direct `xai`, `grok-subscription`, Kimi Code and direct Moonshot integrations are
retired. Catalyst no longer reads Grok login files or ships xAI/Grok profiles or
a stock Grok example. Historical evaluation records remain readable.

**Hosted rollout verified 2026-10-26:** the evaluator now derives provider
availability from Dungeness revision `08e8f7d`; the old three-provider allowlist
has been removed. Anthropic pricing and submission permission were checked over
HTTPS without sending a model credential or starting an evaluation. Direct xAI
and Grok subscription requests are rejected. This admission check does not claim
a paid Anthropic inference test.

The [generic harness implementation](generic-harnesses.md) keeps real credentials
in the trusted gateway. The older native-agent execution route is retired.

For supported providers, use the
[general source submission flow](generic-harnesses.md#submit-your-own-agent).
The provider/model belongs to the run configuration. There is no required
provider-specific harness and no model account registration on the server.

Submit source with the provider, model, reasoning effort and spending cap in
`evaluation.json` or the per-run CLI flags.
For example, a compatible Codex harness can select `openai-chatgpt`,
`gpt-6-astra`, high reasoning effort and a one-credit cap. The server builds the source and runs its entrypoint
inside Dungeness against the pinned ECDSA problem.

## Which token, and where does it come from?

| Item | Where the user gets it | What it does |
| --- | --- | --- |
| Yukon API key | Sign in to the **dev Yukon website**, open the account's **API keys** page (`/api-keys`), and create a key. An existing dev CLI login also works. | Identifies the solver to Catalyst and Yukon. |
| Temporary ChatGPT access | Sign in locally with Codex; Catalyst reads the login file automatically. No manual token extraction is needed. | Allows this run to call the selected model through Dungeness. |
| Verification receipt | Catalyst writes `HARNESS_DIRECTORY/verification.json` after a successful `remote submit --wait`. The CLI prints its exact path. | Identifies the verified execution, harness and problem for Yukon. It is not a login credential. |
| GitHub OIDC token | GitHub Actions obtains it automatically. | Authenticates the hosted workflow when it retrieves the receipt. Users do not create or copy it. |

This deployment uses `https://api-dev.yukon.org`. A production key from
`www.yukon.org` will not work here; use the dev website supplied by the operator.
There is no separate `CATALYST_API_TOKEN` for normal users.

### First-time login

If already logged into Yukon dev, reuse that login. Otherwise, supply the dev
key privately in the terminal where you will run Catalyst and Yukon:

```sh
export YUKON_API_URL=https://api-dev.yukon.org
# Paste the dev key at the following hidden prompt, then press Enter.
read -r -s YUKON_API_TOKEN
export YUKON_API_TOKEN
```

For ChatGPT, reuse an existing `~/.codex/auth.json`. This MVP reads file-based
Codex credentials. If that file is absent, create a file-based login where your
workspace's authentication policy permits it:

```sh
codex -c 'cli_auth_credentials_store="file"' login
codex -c 'cli_auth_credentials_store="file"' login status
```

Complete the browser sign-in with ChatGPT. Codex can otherwise store credentials
in an OS keyring, which this MVP does not read. See
[OpenAI's authentication documentation](https://learn.chatgpt.com/docs/auth).
For a custom login-file location, pass
`--codex-auth-file /absolute/path/to/auth.json`.

### Submit source and obtain the receipt

```sh
export CATALYST_EVALUATOR_URL=https://3.21.93.126
unset CATALYST_API_TOKEN CATALYST_LOCAL_TEST CATALYST_LOCAL_ECDSA CATALYST_LOCAL_PROBLEM_SET
uv run catalyst remote submit .catalyst/my-harness \
  --provider openai-chatgpt --model gpt-6-astra --reasoning-effort high --budget 1 \
  --codex-auth-file --wait
```

The resulting receipt is `.catalyst/my-harness/verification.json`.
Create `submission/` and copy the complete file into the Yukon checkout's
`submission/verification.json`;
do not extract an authentication token or invent a score. If waiting was
interrupted, use `catalyst remote wait EVALUATION_ID` to retrieve the same run.
See [the complete Yukon submission commands](github-actions-e2e.md#solver-commands).

Yukon dev login authenticates the solver. `--codex-auth-file` reads the existing
ChatGPT login from `~/.codex/auth.json` (or an explicit path). Only access token,
ID token, account ID and login timestamp cross the authenticated HTTPS connection. The renewable
refresh token stays on the client. Credentials are excluded from source packages,
request JSON, databases, receipts and public results.

The API holds credentials in memory and delivers them once to its worker over a
private inherited socket. The worker stages authentication in Linux
`/dev/shm` tmpfs with private permissions. In current generic execution, only
the trusted gateway receives real provider access; the harness uses a placeholder
credential and the gateway endpoint from `CATALYST_TASK`. Staging is removed
when execution finishes. Core dumps and swap must remain disabled.
The earlier native Codex route exposed temporary access to the harness container;
that historical route has weaker credential isolation.
Refresh credentials are never delivered. Provider expiry requires fresh access.
A service restart loses queued credentials and fails affected jobs without
silently restarting inference.

Dungeness provides token accounting and enforces the configured budget between
responses. Its token limit uses the native cache-weighted budget counter;
Catalyst checks that counter against the terminal ledger while retaining raw
provider token counts for credit pricing. A final in-flight response can exceed the cap. Catalyst retains the
actual usage. Validity policy v3 accepts in-flight overshoot only with trusted
evidence that every charged request started before budget exhaustion;
it never clips usage to manufacture eligibility. Normalized credits use pinned
prices and do not imply a ChatGPT subscription incurs a cash charge.

## Service operation

Provider configuration and deployment are maintained in the private `catalyst-verifier` repository. Solvers use the public credential options above.
