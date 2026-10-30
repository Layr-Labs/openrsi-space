# Verifier endpoint

The dedicated OpenRSI VM serves **https://3.21.93.126** with a trusted
Let's Encrypt IP certificate and automatic renewal. No third-party hostname
or SSH tunnel is required.

```sh
export CATALYST_EVALUATOR_URL=https://3.21.93.126
export YUKON_API_URL=https://api-dev.yukon.org
```

Use the existing Yukon dev login. The benchmark remains
`layr-labs/catalyst`, UUID `8d3a2daa-afab-4685-b93a-7443c83049d2`, in Pareto
mode. Hosting the verifier on the production VM does not change the Yukon
account environment.

The challenge-owned GitHub workflow uses this same HTTPS endpoint. Its GitHub
OIDC authentication, receipt checks, problem binding and source binding are
unchanged. Receipt retrieval never starts Dungeness or spends model credits.
Existing Openclaw evaluations were copied with their original IDs and evidence.

Yukon pins the trusted repository revision. The benchmark owner must refresh
that revision through Yukon's existing Pareto reorg operation and verify the
hosted receipt checks before resuming submissions. Publishing a workflow change
alone does not replace the benchmark's active pinned revision.

The current IP must remain assigned to this instance. A permanent domain can
be added later using an Elastic IP and an A record, followed by a hostname
certificate and another trusted endpoint update.
