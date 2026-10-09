# Temporary model access

The MVP uses Dungeness's native Codex/ChatGPT provider. Submit source with the
provider, model, reasoning effort and spending cap in `evaluation.json`.
`harnesses/ecdsa-research` selects `openai-chatgpt`, `gpt-6-astra`, `high`, and
one normalized model credit. The server builds the source and runs its entrypoint
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
export CATALYST_EVALUATOR_URL=https://35.92.254.142
unset CATALYST_API_TOKEN CATALYST_LOCAL_TEST CATALYST_LOCAL_ECDSA CATALYST_LOCAL_PROBLEM_SET
.venv/bin/catalyst remote submit harnesses/ecdsa-research \
  --codex-auth-file --wait
```

The resulting receipt is `harnesses/ecdsa-research/verification.json`.
Copy the complete file into the Yukon checkout's `submission/verification.json`;
do not extract an authentication token or invent a score. If waiting was
interrupted, use `catalyst remote wait EVALUATION_ID` to retrieve the same run.
See [the complete Yukon submission commands](github-actions-e2e.md#solver-commands).

Yukon dev login authenticates the solver. `--codex-auth-file` reads the existing
ChatGPT login from `~/.codex/auth.json` (or an explicit path). Only access token,
ID token, account ID and native login timestamp cross the authenticated HTTPS connection. The renewable
refresh token stays on the client. Credentials are excluded from source packages,
request JSON, databases, receipts and public results.

The API holds credentials in memory and delivers them once to its worker over a
private inherited socket. The worker stages native Codex authentication in Linux
`/dev/shm` tmpfs with private permissions. Dungeness's generated per-run launcher
also uses tmpfs; the submitted example keeps its Codex home there. Staging is
removed when execution finishes. Core dumps and swap must remain disabled.
Native subscription mode exposes temporary access to the harness container;
it is reduced credential isolation, not a revocable per-run provider token.
Refresh credentials are never delivered. Provider expiry requires fresh access.
A service restart loses queued credentials and fails affected jobs without
silently restarting inference.

Dungeness provides token accounting and enforces the configured budget between
responses. Its token limit uses the native cache-weighted budget counter;
Catalyst checks that counter against the terminal ledger while retaining raw
provider token counts for credit pricing. A final in-flight response can exceed the cap. Catalyst retains the
actual usage and rejects over-cap results under the current scoring contract;
it never clips usage to manufacture eligibility. Normalized credits use pinned
prices and do not imply a ChatGPT subscription incurs a cash charge.

## Operator enablement

Keep existing identities and receipt policies. Add `model_policy` to `auth.json`:

```json
{
  "model_policy": {
    "enabled": true,
    "providers": ["openai-chatgpt"],
    "limits": {"max_model_tokens": 1000000, "max_seconds": 900}
  }
}
```

Set `worker.json`'s `model_access` to `"temporary"`. Restart only with no active
jobs. This route needs Linux tmpfs and the pinned Dungeness ChatGPT support.
Baseline jobs remain available. No new model-accounting proxy is required.
The worker exports Dungeness’s existing intermediate evaluator history and
retains the independently checked final candidate. History export and candidate
screening are deployed in `20261008-history-screen-1`. Credential renewal and
user cancellation remain separate work.
