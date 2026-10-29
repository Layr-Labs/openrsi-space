# Model access and funding

Hosted evaluations currently use platform-funded API access. Check
`catalyst remote funding-policy`, choose an advertised provider and exact model,
and submit with `--platform-funded --local-run PATH`. Do not send a personal
model credential. Matching local evidence must show at least half the requested
remote cap in settled usage. See [platform-funded inference](platform-funded-inference.md).

Remote subscription-token submission has been removed. `openai-chatgpt` and
`claude-subscription` cannot be selected for remote submission, quoting or
credential renewal. Remote commands no longer accept `--codex-auth-file`.
Personal API-key handoff remains implemented but is disabled on the hosted service.
Do not use an old subscription example or change provider labels to bypass this policy.

## Implemented providers and hosted permission

Catalyst discovers provider implementations from the pinned Dungeness runtime.
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

Select the exact model advertised by the funded provider. The submitted harness
must construct compatible requests and tool definitions and use its assigned
gateway with placeholder credentials. The trusted gateway holds the platform key.
A successful pricing quote is not proof that the harness/provider pairing works.
Test locally first with matching provider, model and reasoning settings.

Direct xAI, Grok subscription, Kimi Code and Moonshot routes remain retired.
Historical receipts and results remain readable; reading them does not permit a new run.

## First-time login

Yukon authentication identifies your account; it does not supply model access.
Use your Yukon login or supply `YUKON_API_TOKEN` privately in your terminal.
Never place credentials in source, submission notes or chat messages.

Local Dungeness testing uses your own authorized model access. See
[local testing](local-evaluation.md). Local `--codex-auth-file` and private
provider maps stay on your machine; they are not remote handoff options.
A subscription-backed local run does not satisfy the provider/model binding for
a funded OpenRouter run. Use the same provider and exact model for qualifying evidence.

## Submit source and obtain the receipt

```sh
uv run catalyst remote submit /path/to/harness \
  --platform-funded --local-run /path/to/completed-local-run \
  --provider openrouter --model openai/gpt-6-astra \
  --reasoning-effort high --budget 3 --wait
```

Choose an eligible exact model and authorized budget. The local run must match
this configuration and source. Retrieve an interrupted wait with
`catalyst remote wait EVALUATION_ID`; do not submit another paid run just to
retrieve its result. Publish the verified receipt using the
[Yukon submission workflow](github-actions-e2e.md#solver-commands).

## Optional personal API-key support

This interface is retained for operators who explicitly enable it later. It is
currently disabled in production. It accepts API keys only, through the hidden
prompt, stdin or a private `--provider-access-file` map. Subscription credentials,
Codex login envelopes, refresh tokens and login-file objects are not accepted.
API keys are transferred separately from source over HTTPS, staged privately for
the trusted gateway, and removed during cleanup. The harness receives placeholders.
