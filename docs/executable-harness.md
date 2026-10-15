# Executable harness development

Create your agent in its own directory, using the starter generator or your own
repository. Catalyst packages that source for the remote verification service.
After a successful evaluation, copy the returned receipt to the challenge
checkout's generated `submission/verification.json`; `yukon run` checks that retained result.
See [the solver guide](solver-guide.md) for authentication and publication.

The problem is **ecdsa.fail**. Exact source commits, candidate paths and verifier
commands live in `src/catalyst/problem-set/initial.json`. Local checks use that
pin; they cannot issue an official receipt.

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
uv run catalyst harness create my-solver --output .catalyst/my-solver
uv run catalyst harness build .catalyst/my-solver
```

The build prints its `id`. Use it to run the complete entrypoint:

```sh
uv run catalyst harness smoke BUILD_ID \
  --workspace ./work/ecdsa --problem ecdsa.fail
```

Smoke tests use a **copy** of the workspace, without network access or model
credentials. Records live under `.catalyst/smoke/`. They test entrypoint
execution, not problem verification or performance. The starter leaves the
starting candidate unchanged and makes no model calls. It is only a packaging
smoke test: the default blank scaffold is not a valid circuit, so this starter
cannot earn a verified score until you implement the research agent.

Replace `agent.py` with your solver. Install runtime dependencies and problem
toolchains in its Dockerfile. Python 3 and Bash are required for the platform
launcher and Dungeness clients; the solver can use any language.
The starter copies the whole bundle into `/opt/harness/`, so knowledge files,
prompts and helper modules travel with the agent. Use the
[general remote submission flow](generic-harnesses.md#submit-your-own-agent)
to choose provider, model and budget separately from those source files.

The `execution` field in the ordinary harness manifest is:

```json
{
  "interface": "catalyst-exec-v1",
  "dockerfile": "Dockerfile",
  "entrypoint": ["python3", "/opt/harness/agent.py"]
}
```

Executable packages cannot select a host agent or Python adapter. Knowledge,
memory, indexes and retrieval tools belong inside the harness image, using any
layout the agent supports. There is no platform knowledge-base service, lookup
command or injected reading policy. Legacy instruction-only agent references
cannot attach a `knowledge/` bundle; migrate those files into an executable
harness instead.

`CATALYST_TASK` points to a JSON file containing problem/harness references,
instruction, writable workspace, candidate paths, budget, model and gateway
URL, plus an allowed `models` list. `CATALYST_WORKSPACE`, `CATALYST_MODEL`
and `CATALYST_MODELS` are convenience variables.
With the [problem-service runtime](problem-service.md), the launcher first fetches
the server-assigned statement and checks its SHA-256, problem identity and
candidate paths. The resolved task includes `problem_document`, and
`CATALYST_PROBLEM_URL` points to the read-only document. A failed or mismatched
fetch stops the launcher before your entrypoint runs.
During Dungeness execution, `OPENAI_BASE_URL` points at the metered gateway
and `OPENAI_API_KEY` is only the public placeholder `testbed`. Smoke tests
supply no gateway or model.

Write candidate files under the workspace and exit zero on success. The
independent verifier judges the candidate; submitted stdout or claimed scores
never establish official observations. Never put provider credentials in
source or images.

## Official evaluation

Submit the harness source using the [solver guide](solver-guide.md). The remote service builds and runs it with metered model access and independent verification. Operator Dungeness tooling lives in `catalyst-verifier`; it is not required locally.
