# Local checks before a remote run

You do not need Dungeness or the private verification service to prepare a harness.
Choose the depth of testing you need: verify a circuit, smoke-test a package,
or run the full autonomous agent locally with Dungeness.

## Check a candidate circuit

```sh
uv run catalyst problem clone ecdsa.fail .catalyst/ecdsa-workspace
uv run catalyst problem setup ecdsa.fail --workspace .catalyst/ecdsa-workspace
uv run catalyst problem check ecdsa.fail --workspace .catalyst/ecdsa-workspace
```

The clone is pinned. Edit only the allowed candidate paths. These commands use
the upstream verifier on your machine; setup can download dependencies. They do
not run a research agent, isolate all networking or meter model usage, and their
scores are not official remote evidence.

## Check harness packaging and its entrypoint

```sh
uv run catalyst harness create my-agent --executable --output .catalyst/my-agent
uv run catalyst harness build .catalyst/my-agent
uv run catalyst harness smoke BUILD_ID --workspace .catalyst/ecdsa-workspace --problem ecdsa.fail
```

Replace `BUILD_ID` with the build command's returned `id`. The smoke test runs
on a copied workspace with no network, model access or host credentials. This
checks packaging and launch behavior, not research quality.

## Optional full agent run with Dungeness

[Dungeness](https://github.com/Layr-Labs/dungeness) is the publicly available
research runtime used by Catalyst's remote service. Anyone can clone it:

```sh
git clone https://github.com/Layr-Labs/dungeness.git
```

Local testing with it is optional and does not require the private
`catalyst-verifier` service. Follow Dungeness's README and
[command-harness guide](https://github.com/Layr-Labs/dungeness/blob/main/docs/command-harness.md)
to install its dependencies, register your harness, and configure a run spec.
Use the same pinned ECDSA problem/checkpoint and compatible runtime version as
the remote service when comparing results. A Catalyst source package is not
itself a Dungeness run spec; follow the harness adapter instructions.
The public `main` branch and the deployed service may use different revisions;
public repository access alone does not establish matching runtime behavior.

Dungeness can run the agent, meter gateway usage and verify intermediate and
final candidates locally. The harness must use its declared metered endpoints.
Model-enabled tests consume your own API credits or subscription allowance:
choose limits and authorize model use before running them. Linux is required
for the current clean no-network final verifier; macOS supports development
and agent/sidecar runs but does not establish equivalent final verification.

Local runs are useful development evidence, **not official Catalyst results**.
They cannot issue a receipt accepted by Yukon. When ready, submit the source
to Catalyst so the service runs it under its pinned conditions and independently
records the official scores and usage.

## Move to the official evaluation

When ready, follow the [solver guide](solver-guide.md) to submit the source and
temporary model access to the remote service. After receiving the receipt,
`yukon run` retrieves and validates that retained result without starting another run.

Operator tests involving the API, Dungeness, gateway or a mock model provider live
in `catalyst-verifier`. Solvers do not need that private checkout.
