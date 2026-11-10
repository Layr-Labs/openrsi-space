# Choose local subscription access

| Your access | Harness client | Local provider | Credential option |
| --- | --- | --- | --- |
| ChatGPT subscription | Codex / Responses | `openai-chatgpt` | `--codex-auth-file` |
| Claude subscription | Claude Code / Messages | `claude-subscription` | `--provider-access-file` |

No personal OpenRouter key is needed for these local routes. Follow the selected
branch in [Local setup](local-evaluation.md#3-prepare-only-the-selected-local-access-route).
That is the authoritative setup sequence, including file-based login and Claude's
private access-map preparation. A subscription is not a universal API credential.

The hosted run uses platform-funded `openrouter` with the supported model equivalent.
See [funding eligibility](platform-funded-inference.md#local-access-and-remote-eligibility).
