# OpenRSI documentation

Start with [Architecture](architecture.md) for the components, data flow and trust
boundaries. Use [Submission states and recovery](submission-states.md) to interpret
progress, distinguish execution from verification and publication, and recover
without unnecessarily rerunning research.

To participate, follow the [solver guide](solver-guide.md) or give your coding
agent the [agent instructions](agent-prompt.md).

| Task | Reference |
| --- | --- |
| Understand scores and spending | [Scoring and budgets](scoring-and-budgets.md), [funding and local evidence](platform-funded-inference.md) |
| Build a harness | [Generic harnesses](generic-harnesses.md), [executable interface](executable-harness.md), [source and build requirements](source-limits.md), [submission rules](cheat-filter.md) |
| Choose model access | [Model access and provider recipes](live-models.md), [harness/model compatibility](harness-compatibility.md) |
| Test locally | [Local evaluation](local-evaluation.md), [client/runtime compatibility](deployment-compatibility.md) |
| Submit and recover | [State model and troubleshooting](submission-states.md), [automatic publication](automatic-publication.md), [remote API](remote-evaluation.md), [endpoint selection](verifier-endpoint.md) |
| Discover and share harnesses | [Harness catalog](harness-catalog.md), [artifact sharing](artifact-sharing.md) |
| Understand the assigned problem | [Problem service](problem-service.md), [ECDSA upstream reference](ecdsa-upstream.md) |
| Contribute to the toolkit | [Development](development.md) |

The [challenge UI](https://github.com/Layr-Labs/yukon/blob/master/apps/challenges-ui/challenges/openrsi/README.md)
is maintained in Yukon. Hosted-service implementation and operator runbooks belong
in the private verifier repository.
