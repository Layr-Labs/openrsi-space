# Stock Grok subscription harness

This example runs Grok CLI 1.0.62 through Catalyst's assigned gateway using
`grok-subscription/grok-4.7`. The actual subscription credential stays in the
gateway; the agent receives only a placeholder. Build dependencies are installed
in the image because research-time public internet access is disabled.

The CLI's main agent uses Chat Completions, but its session-title helper uses
Responses. `gateway_adapter.py` translates that helper request and response,
including nested function tools and named tool choice, to Chat Completions.
Selecting a provider or changing the model name alone cannot do this translation.
See [the compatibility guide](../../docs/harness-compatibility.md) before adapting
this example to another framework or provider.

After authorizing remote use of your subscription and configuring Yukon login
and the evaluator URL:

```sh
uv run catalyst harness build examples/stock-grok
uv run catalyst remote submit examples/stock-grok --grok-auth-file --wait
```

The included evaluation settings use 3 normalized model credits, 1,000,000
tokens and 2700 seconds (45 minutes). These credits measure reference-priced usage rather than
your remaining subscription allowance. No API-key fallback is configured.
Keep `~/.grok/auth.json` outside the source package.

The original remote run confirmed subscription access but stopped on a malformed
session-title tool definition. The adapter regression tests exercise the corrected
format with a strict mock upstream. They do not establish a successful live run
or a valid circuit from the corrected harness.
