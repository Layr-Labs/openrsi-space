# Codex ECDSA research

This submitted source runs Codex 0.153.3 through Dungeness's native ChatGPT route.
The server builds the Dockerfile, supplies the pinned ECDSA workspace and temporary
access, and independently verifies the final point-add candidate.

`evaluation.json` selects `openai-chatgpt`, `gpt-6-astra`, high reasoning effort,
a $1 normalized credit budget, 100,000 tokens and 900 seconds. Dungeness accounts
for model usage. Its budget is checked between responses, so the last response
can exceed the cap. The current scoring contract rejects over-cap results.
The prompt asks for a brief inspection and one small, checked optimization.
An improvement is not guaranteed.

```sh
export CATALYST_EVALUATOR_URL=https://35.92.254.142
.venv/bin/catalyst remote submit harnesses/ecdsa-research --codex-auth-file --wait
```

Use an existing Yukon dev login and a local Codex ChatGPT login. Renewable
credentials stay local. Temporary access travels over HTTPS and is staged in RAM
for native Codex authentication. See [credential handling](../../docs/live-models.md).
