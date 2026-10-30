# Local Grok subscription testing

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
