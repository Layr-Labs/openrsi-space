# Temporary model access

The MVP uses Dungeness's native Codex/ChatGPT provider. Submit source with the
provider, model, reasoning effort and spending cap in `evaluation.json`.
`harnesses/ecdsa-research` selects `openai-chatgpt`, `gpt-6-astra`, `high`, and
one normalized model credit. The server builds the source and runs its entrypoint
inside Dungeness against the pinned ECDSA problem.

```sh
export CATALYST_EVALUATOR_URL=https://35.92.254.142
unset CATALYST_LOCAL_TEST CATALYST_LOCAL_ECDSA CATALYST_LOCAL_PROBLEM_SET
.venv/bin/catalyst remote submit harnesses/ecdsa-research \
  --codex-auth-file --wait
```

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
    "limits": {"max_model_tokens": 100000, "max_seconds": 900}
  }
}
```

Set `worker.json`'s `model_access` to `"temporary"`. Restart only with no active
jobs. This route needs Linux tmpfs and the pinned Dungeness ChatGPT support.
Baseline jobs remain available. No new model-accounting proxy is required.
Only the final candidate is captured; intermediate checkpoint collection,
credential renewal and user cancellation remain separate work.
