# Executable harness development

For the Yukon solver entrypoint, run `yukon setup` and `yukon run` from the
Catalyst root, then edit `submission/`. The root `benchmark.json` connects those
commands to the remote evaluation bridge. An older CLI needs `yukon update`.
Remote runs require a configured evaluator and a private grant reference;
the server is not connected yet. Submission reuses a matching remote result
without another paid run. See [the remote contract](remote-evaluation.md).
The commands below also document the standalone
Catalyst tooling and individual real-problem development checks.

The initial problem is **ecdsa.fail**. Exact source commits, candidate paths and verifier commands live in
`src/catalyst/problem-set/initial.json`. The CLI does not follow a moving frontier.

Executable source packaging, local Docker builds, offline image smoke tests,
a generic Dungeness adapter, and the remote HTTP client/workflow are implemented.
A persistent local API and Dungeness worker execute the actual pinned ECDSA
baseline with model access disabled. A smaller circuit fixture tests model
accounting and Yukon integration; see [the local checks](local-evaluation.md).
Those local modes use fixture identities. The [private VM service](remote-vm.md)
uses provisioned account keys and a dedicated Yukon consumer key. Temporary
provider access and release of the hosted Yukon retrieval provider remain pending.

## Develop against a problem

```sh
uv run catalyst problem list
uv run catalyst problem clone ecdsa.fail ./work/ecdsa
uv run catalyst problem setup ecdsa.fail --workspace ./work/ecdsa
uv run catalyst problem check ecdsa.fail --workspace ./work/ecdsa
```

Edit `src/point_add`. Checks reuse the existing workspace and build caches;
trusted contract edits are rejected. Local feedback is not official evidence.
The pinned start is `62ae3d00d1e01d7bc640b5163cfea8dabffd8392`, also used by
the Dungeness task/checkpoint binding. Full circuit simulation is memory
intensive and is separate from the lightweight local contract tests.

## Package and smoke-test a harness

```sh
uv run catalyst harness create my-solver --executable
uv run catalyst harness build harnesses/my-solver
```

The build prints its `id`. Use it to run the complete entrypoint:

```sh
uv run catalyst harness smoke BUILD_ID \
  --workspace ./work/ecdsa --problem ecdsa.fail
```

Smoke tests use a **copy** of the workspace, without network access or model
credentials. Records live under `.catalyst/smoke/`. They test entrypoint
execution, not problem verification or performance. The starter leaves the
starting candidate unchanged and makes no model calls.

Replace `agent.py` with your solver. Install runtime dependencies and problem
toolchains in its Dockerfile. Python 3 and Bash are required for the platform
launcher and Dungeness clients; the solver can use any language.

The `execution` field in the ordinary harness manifest is:

```json
{
  "interface": "catalyst-exec-v1",
  "dockerfile": "Dockerfile",
  "entrypoint": ["python3", "/opt/harness/agent.py"]
}
```

Executable packages cannot select a host agent or Python adapter. Legacy
instruction/knowledge packages remain supported.

`CATALYST_TASK` points to a JSON file containing problem/harness references,
instruction, writable workspace, candidate paths, budget, model and gateway
URL. `CATALYST_WORKSPACE` and `CATALYST_MODEL` are convenience variables.
During Dungeness execution, `OPENAI_BASE_URL` points at the metered gateway
and `OPENAI_API_KEY` is only the public placeholder `testbed`. Smoke tests
supply no gateway or model.

Write candidate files under the workspace and exit zero on success. The
independent verifier judges the candidate; submitted stdout or claimed scores
never establish official observations. Never put provider credentials in
source or images.

## Prepare an executable Dungeness attempt

This is a local development path with arbitrary test allowances. Official remote
evaluations use only the two checkpoints and Best achieved and [trusted accounting](tier-accounting.md).
The current adapter does not collect official checkpoint seals.

With the existing Dungeness installation configured:

```sh
uv run catalyst problem create ecdsa-start \
  --task task:users/bx/ecdsa-fail-v2 \
  --checkpoint checkpoint:public/github/layr-labs/ecdsafail-challenge/62ae3d00d1e01d7bc640b5163cfea8dabffd8392

uv run catalyst evaluate problems/ecdsa-start harnesses/my-solver \
  --build BUILD_ID --model gpt-5.6-sol --budget 1 --prepare-only
```

Preparation inspects the Docker image but starts no containers or model calls.
One trusted Harbor adapter is installed in a disposable Dungeness checkout.
Dungeness adds the frozen workspace, candidate transfer, verifier and metering.
The built starter lacks Rust: add the pinned toolchain and offline dependencies
before attempting a full ecdsa.fail run.

Repeat preparation with the same source/build to create another attempt,
including with another model or budget. Source and build identities remain
unchanged. Unbuilt source changes are rejected. Prepared attempts record the
source digest, image ID and Dungeness pin; imported local results retain the
build reference.

`image_id` is Docker's immutable local image/config ID, **not** a registry
manifest digest. BuildKit uses a content-named local tag, checked against that
ID before execution. A production worker must build the source itself and
record its pushed registry digest; client build records are not trusted.

The local builder is not a multi-tenant build sandbox. Dedicated worker
isolation, private model authorization, trusted checkpoint capture and
trusted result publication remain necessary before launch.
