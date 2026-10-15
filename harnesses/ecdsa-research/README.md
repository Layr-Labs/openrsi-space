# Codex ECDSA research

This submitted source runs Codex 0.153.3 through Dungeness's native ChatGPT route.
The server builds the Dockerfile, supplies the pinned ECDSA workspace and temporary
access, and independently verifies the final point-add candidate.

`evaluation.json` selects `openai-chatgpt`, `gpt-6-astra`, high reasoning effort,
a $1 normalized credit budget, a secondary ceiling of 1,000,000 tokens and
900 seconds. The generous token ceiling lets the credit cap govern spending
instead of stopping cached multi-turn research prematurely. Dungeness accounts
for model usage. Its budget is checked between responses, so the last response
can exceed the cap. The current scoring contract rejects over-cap results.
The prompt reads the configured cap, checks the starting candidate and small
optimizations, and asks the agent to finish by 85% of the cap to leave room for
its final response. Change `max_model_credits` in a copy of `evaluation.json`
to choose another cap.
An improvement is not guaranteed.

```sh
export CATALYST_EVALUATOR_URL=https://3.21.93.126
.venv/bin/catalyst remote submit harnesses/ecdsa-research --codex-auth-file --wait
```

Use an existing Yukon dev login and a local Codex ChatGPT login. Renewable
credentials stay local. Temporary access travels over HTTPS and is staged in RAM
for native Codex authentication. See [credential handling](../../docs/live-models.md).
