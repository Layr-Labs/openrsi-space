# Local MiniMax subscription testing

Use your MiniMax Coding/Token Plan key with `minimax-subscription`, the exact
supported model (`MiniMax-M3.1-Flash` or `MiniMax-M3`), and Chat Completions through
the assigned gateway. A subscription key and a pay-as-you-go API key may have
similar interfaces; select the plan key to consume your subscription.

Supply it privately through a local environment variable or a 0600 credential
map outside the harness. Never put the key in source or command arguments.

```sh
uv run openrsi-space local run /absolute/path/to/harness \
  --dungeness /absolute/path/to/dungeness \
  --provider minimax-subscription --model MiniMax-M3.1-Flash \
  --budget 3 --provider-token-env MINIMAX_PLAN_KEY \
  --pricing /absolute/path/to/dungeness/docs/examples/local-subscription-pricing-20261030.json
```

Set `MINIMAX_PLAN_KEY` privately before running. The harness receives only a
placeholder; the gateway substitutes the key and records provider-reported usage.
Preserve the assistant's reasoning content and tool calls in conversation history,
as required by the [MiniMax API](https://platform.minimax.io/docs/api-reference/text-openai-api).

Credits use a frozen reference schedule, not an assertion of cash billing or
remaining subscription allowance. Remote credential submission remains disabled;
this route does not change funded remote evaluation or evidence eligibility.
Live account compatibility must be checked separately from synthetic tests.
