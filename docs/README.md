# OpenRSI documentation

## Start here

**Coding agents:** start with [For agents](agent-prompt.md). It directs you through
[Local setup](local-evaluation.md), the selected model-access recipe, harness preparation,
local testing and remote submission. Read detailed references only when that step
needs them. Report progress and identify whether a blocker needs human action.

**Solvers:** use [Quickstart](solver-guide.md) to follow the same journey yourself,
or give the agent your research idea, preferred model access and testing budget.
Local ChatGPT/Codex and Claude subscription tests do not require an OpenRouter key.
Eigen Labs supplies remote model access.

## Find the answer for your current step

| Question | Authoritative guide |
| --- | --- |
| Is this machine ready, and how do I use my login? | [Local setup](local-evaluation.md) |
| What must my harness implement? | [Build a harness](executable-harness.md) |
| How must the wrapper recover from gateway errors? | [Harness compatibility](harness-compatibility.md) |
| Where is my submission, and what can happen next? | [Submission states](submission-states.md) |
| What failed, and can I retry without another run? | [Troubleshooting](submission-recovery.md) |
| Which model routes and credentials are supported? | [Model access](live-models.md) |
| How do caps, usage and funding eligibility work? | [Funding and scoring](platform-funded-inference.md) |
| What source can I submit? | [Source limits and research rules](source-limits.md) |
| What is public, and how do I reuse or publish source? | [Artifacts, licenses and optional publication](artifact-sharing.md) |
| How do configuration and task documents work? | [Harness configuration](generic-harnesses.md) |

## System and maintainer references

- [Architecture](architecture.md)
- [Runtime compatibility and release pins](deployment-compatibility.md)
- [Development](maintainers/development.md)
- [Remote API contract](maintainers/remote-api.md)

Each topic has one home; there is no mirrored reference directory to read as well.
