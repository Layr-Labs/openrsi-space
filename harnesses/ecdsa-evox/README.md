# EvoX on ECDSA

This runs the real SkyDiscover EvoX algorithm at commit
`0d932b690670a7e544388ad362e9876c8bd256a0`. The small adapter represents the
edits to the editable Rust directory as a JSON list, calls Dungeness's trusted
`evaluate --json` for every proposed candidate, and retains verified improvements.
EvoX still controls candidate generation and evolution of its search strategy.
Each edit uses an exact, unique old/new string replacement against the original
baseline. Overlapping edits are rejected. Unchanged source remains intact.
The smoke configuration supplies at most 30,000 characters of source excerpts;
it does not ask the model to rewrite the roughly 389 KB starting module.
This limits the smoke agent's research context, not the platform's harness interface.

The image installs upstream code and its frozen Python dependencies at build
time. Runtime has no internet. Main, guide and meta-search models all use the
declared gateway model set; no upstream default model can silently incur costs.
Model keys are never included in this source or image.
The included `skydiscover-compat.patch` omits empty system messages from upstream's
Chat Completions client. It also uses K3's `max_completion_tokens` parameter and
omits sampling parameters, for which K3 requires fixed defaults. Nonempty
research prompts and the EvoX algorithm are unchanged. A metered startup probe
checks this model configuration before expensive circuit grading.

The default is three solution iterations with Kimi Code `k3`, a $3 normalized
credit cap and a 15-minute agent limit. EvoX also makes metered calls for startup
probes and variation guidance; three iterations does not mean three model calls.
A short run checks integration, not EvoX's research performance.

After generic execution is deployed and `kimi-code` is enabled:

```sh
uv run catalyst remote submit harnesses/ecdsa-evox --prompt-model-token --wait
```

Supply the Kimi Code membership API key at the hidden prompt. A Moonshot
platform key is a different provider. `--budget`, `--max-tokens`, and
`--max-seconds` can override the evaluation defaults.

Status: Docker execution, live Kimi access, official ECDSA verification, and
Yukon publication of this harness have not yet been completed. Offline tests
use synthetic model responses and evaluator results.

The optional `test_evox_harness` integration test runs the actual pinned
framework and OpenAI SDK through an in-memory HTTP transport, checking that
candidate, guide and meta-search requests all use the declared gateway.
Set `CATALYST_SKYDISCOVER` to a checkout of the pinned commit and run the test
with the framework's Python dependencies installed and `skydiscover-compat.patch`
applied (as the Dockerfile does). The 2026-10-09 check used
locally cached dependencies because a fresh frozen install could not reach
the Python package download host.
