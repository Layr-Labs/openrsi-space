# Grok model access

Choose the credential method separately from your harness. An OpenRouter account
is optional. Your Yukon key only identifies you; model requests use your model
account. Updating Catalyst is required to get the new flags:

```sh
git pull --ff-only origin main
uv sync
```

| Access | Provider | Model | Credential option |
| --- | --- | --- | --- |
| Grok CLI subscription session | `grok-subscription` | `grok-4.7` | `--grok-auth-file` |
| Direct xAI API account | `xai` | `grok-4.7` | `--prompt-model-token` |
| OpenRouter API account | `openrouter` | `x-ai/grok-4.7` | `--prompt-model-token`; operator must enable inference-only routing |

## Use your Grok CLI login

Sign in on your own computer with the official Grok CLI:

```sh
grok login --device-auth
uv run catalyst remote submit /path/to/harness \
  --provider grok-subscription --model grok-4.7 --budget 3 \
  --grok-auth-file --wait
```

`--grok-auth-file` defaults to `~/.grok/auth.json`; optionally supply another path.
Catalyst reads one unexpired first-party session and sends only its temporary
access token and expiry to the evaluator. Refresh credentials and account
identity stay local. API-key entries and ambiguous multiple accounts are rejected.
Keep the login file outside your harness directory. Do not paste a token into
source, agent prompts, chat, or a command argument.

Dungeness sends inference through the Grok CLI proxy, with gateway-owned
credentials and an allowed model in the request body. The gateway identifies
itself as `dungeness-gateway/1`; it does not add Grok CLI identity, version,
authentication-response, or model-override headers. The submitted agent cannot switch the
upstream, credentials, or model through request headers. There is no automatic
fallback to an xAI API key. Expired access stops inference; sign in locally again
and submit a new run, or renew a queued run before model execution starts:

```sh
uv run catalyst remote renew-access EVALUATION_ID --grok-auth-file
```

The session path is intended to use eligible Grok Build allowance. Your account's
entitlements and the upstream service determine access and consumption. A live
Grok subscription request previously succeeded with CLI-specific headers.
Those headers have now been removed; live compatibility without them remains
unverified. The stock harness passes an offline Grok CLI test, which does not
establish subscription endpoint access. It supports the explicit `grok-4.7`
mapping, not a floating `grok-build` alias.

## Use a direct xAI API key

Create an API key in the xAI console and enter it at the hidden prompt:

```sh
uv run catalyst remote submit /path/to/harness \
  --provider xai --model grok-4.7 --budget 3 \
  --prompt-model-token --wait
```

This uses `https://api.x.ai/v1` with API-key authentication. It does not reuse a
CLI session. OpenRouter is used only as a public reference-price catalog; a
solver OpenRouter account or credential is not needed for either direct path.

## Harness and local testing

Use the [stock Grok example](../examples/stock-grok) and
[harness compatibility checklist](harness-compatibility.md) when creating a
Grok harness. The CLI's title helper can use a different API format from its
main agent; both must work through the subscription gateway.

The harness must use the assigned gateway URL and the declared model from its
task input. Grok subscription supports OpenAI-compatible Chat Completions; direct
xAI also exposes Responses. A CLI that insists on its public upstream needs a
base-URL option or a harness adapter. Selecting a provider does not rewrite a
third-party CLI's network behavior. Agent-executed function tools are supported;
provider-hosted web search, remote tools and model fallback are disabled.

A local Dungeness run is optional. Use `catalyst local run ... --grok-auth-file`
with a current clean Dungeness checkout and a trusted `--pricing` snapshot
containing this model. `catalyst harness smoke` tests the container offline;
`remote submit` does not first launch a local Dungeness evaluation.

Budgets are normalized reference credits, including a higher rate strictly above
200,000 input tokens for the current Grok 4.7 catalog entry. Cached input counts
toward that threshold. A listed search charge is excluded because hosted search
is blocked. These credits are not a subscription allowance meter or a guaranteed
cash-billing cap; an in-flight response can exceed the requested cap.

## Adding compatible providers

Operators configure fixed upstreams, supported inference routes, credential
kinds and model/catalog mappings in
[`providers.json`](../src/catalyst/providers.json). Catalyst installs its trusted
registry into the pinned Dungeness runtime before building the gateway. Solvers
cannot supply provider profiles or upstream URLs through a run request. Enable
new provider IDs separately in the evaluator's `model_policy.providers`.
OpenAI-compatible token-auth providers normally need a configuration entry;
a different wire protocol or login flow needs a reviewed adapter. Model prices
must still be established from the trusted catalog before a run starts.

The authentication format and CLI proxy follow xAI's
[authentication guide](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/02-authentication.md)
and [shell API documentation](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-shell/README.md#using-authjson-for-api-access).
