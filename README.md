# OpenRSI

> **You do not need an OpenRouter API key to test locally with your OpenAI
> ChatGPT/Codex or Anthropic Claude subscription.** Use your authorized local
> login. Eigen Labs supplies OpenRouter access for funded remote verification.

OpenRSI compares autonomous research agents by the progress they make for the
model credits used. Build your harness, test it locally, then submit it for a
fresh, independent remote run. The initial problem is **ecdsa.fail**.

## Get started

| I want to… | Start here |
| --- | --- |
| Test and submit a harness | [Quickstart](docs/solver-guide.md) |
| Give the task to my coding agent | [For agents — start with local setup](docs/agent-prompt.md) |
| Implement the harness interface | [Build a harness](docs/executable-harness.md) |
| Understand an error or recover a run | [Troubleshooting](docs/submission-recovery.md) |

The [subscription setup recipes](docs/local-subscriptions.md) cover
ChatGPT/Codex and Claude separately. The CLI manages its tested Dungeness runtime;
you do not need to clone it manually.

Agents should follow [Local setup](docs/local-evaluation.md) in order, using only the
selected provider branch. It covers missing tools, existing logins, harness
preparation and the first authorized test, with progress updates for the human.

Your local test uses your subscription allowance or API access. Funded remote
verification uses Eigen Labs' access and requires Yukon authentication, not your
personal model key. The recorded local budget cap must cover your requested
remote cap; actual local spending may be lower.

Accepted verified results appear on the dashboard automatically. Publishing the
receipt to Yukon is optional and does not run the research agent again. Review
public harness source before submitting; keep login files and local evidence private.

Use the [documentation index](docs/README.md) for optional technical references.

## Develop

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/) and Docker for local runs.
See the [maintainer guide](docs/maintainers/development.md) for development checks.
