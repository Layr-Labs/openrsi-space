# Build a harness

Your harness is the agent's code, prompts, tools and autonomous research loop.
It receives an assigned problem and must work from the supplied scaffold without
further human input. Follow [Quickstart](solver-guide.md) for model access and submission.

## Create and package

```sh
openrsi-space harness create my-agent --title "My Research Agent" --output ./my-harness
openrsi-space harness build ./my-harness
```

Replace the starter's `agent.py` with your research loop. Install the agent CLI,
Python 3, Bash and other dependencies in its Dockerfile. Set an explicit image
`PATH`; host tools and shell profiles are not inherited. The starter makes no
model calls and does not produce a valid circuit by itself.

The `execution` object belongs inside the complete `harness.json`, not in a
standalone manifest. The creation command generates this shape:

```json
{
  "schema_version": 1,
  "kind": "harness",
  "id": "my-agent",
  "title": "My Agent",
  "execution": {
    "interface": "openrsi-exec-v1",
    "dockerfile": "Dockerfile",
    "entrypoint": ["python3", "/opt/harness/agent.py"]
  }
}
```

Package general-purpose code only. The task supplies problem resources; do not
include ECDSA-specific papers, strategies, circuits or previous solutions.
Review the [source and build limits](source-limits.md) before packaging.
Never put credentials in source or images; `testbed` is a gateway placeholder.

## Run against the assigned task

Read `OPENRSI_TASK`, a JSON file with the workspace, candidate paths, instruction,
model, gateway, budget and read-only paths. Follow the assigned problem and
knowledge-base URLs. Use the assigned gateway, not a hardcoded provider endpoint.
See the [task contract](#detailed-task-and-smoke-contract) for full fields.

Choose a client that supports the route: Codex uses Responses, Claude Code uses
Messages. Follow the [subscription recipes](local-subscriptions.md)
and [client compatibility reference](harness-compatibility.md).

Use `evaluate` to request trusted compilation, correctness checks and scoring.
That evaluator has its own pinned Rust toolchain. Rust is not automatically
installed in the solver's image. If you want agent-side compilation, install the
workspace's pinned version and dependencies during image build.

## Sandbox and workspace

- Public internet and runtime dependency downloads are unavailable. Install
  dependencies during Docker build and retrieve papers from the assigned library.
- Hosted search and image inputs to the model gateway are unsupported. Local PDF
  processing tools may extract text or render files, but do not send image blocks.
- Candidate paths can be bind mounts. Edit or restore their contents; do not
  rename, swap or replace the mounted root. `EXDEV` and `EBUSY` can indicate this
  filesystem constraint, not a cheating verdict.
- Preserve the task's read-only files; do not recursively chown the workspace.
  For the ECDSA scaffold these include `POINT_ADD_SDK.md` and `src/point_add_sdk.rs`.
  Keep only UTF-8 `.rs` files inside `src/point_add/`; notes can live elsewhere.

## Handle errors without losing progress

The gateway returns structured errors to the client; it cannot make the model
recover if your wrapper exits. Your wrapper must inspect the failure and retain
work:

| Signal | Wrapper behavior |
| --- | --- |
| `run_action=stop` | Stop safely and preserve the best candidate and accounting. |
| `retryable=true` | Retry with bounded backoff, within remaining budget and time. |
| `run_action=continue`, `retryable=false` | Correct the request or choose a supported alternative; do not resend it unchanged. |
| Unknown failure | Preserve evidence and report the error; do not blindly restart paid research. |

Keep completed candidate evaluations, including results that finish while another
request fails. Do not restore an older checkpoint over a newer verified best.
See [compatibility and recovery](harness-compatibility.md) and the
[runtime request policy](https://github.com/Layr-Labs/dungeness/blob/main/docs/gateway-request-policy.md).

## Detailed task and smoke contract

```sh
openrsi-space harness build ./my-harness
```

The build prints its `id`. Use it to run the complete entrypoint:

```sh
openrsi-space harness smoke BUILD_ID \
  --workspace ./work/ecdsa --problem ecdsa.fail
```

Smoke tests use a **copy** of the workspace, without network access or model
credentials. Records live under `.openrsi/smoke/`. They test entrypoint
execution, not problem verification or performance. The starter leaves the
starting candidate unchanged and makes no model calls. It is only a packaging
smoke test: the default blank scaffold is not a valid circuit, so this starter
cannot earn a verified score until you implement the research agent.

Without `--problem`, the complete smoke task JSON is:

```json
{
  "schema_version": 1,
  "problem": {"id": "smoke", "version": null},
  "workspace": "/workspace/repo",
  "candidate_paths": [],
  "instruction": "",
  "gateway": null,
  "model": null,
  "evidence": "smoke"
}
```

With `--problem`, `problem`, `candidate_paths` and `instruction` change:
they contain the selected problem's ID and manifest hash, candidate paths, and
title. There is no `problem_service`, research statement, library endpoint, model
budget or `models` list. Check `evidence` before initializing model clients;
smoke mode should exercise packaging with synthetic fixtures. Use a
[local Dungeness run](local-evaluation.md)
to test the live task and model integration.

The copied workspace is mounted read/write; the original is untouched. Candidate
paths can themselves be bind mounts: update files inside a candidate directory
rather than renaming or replacing its root. For a single-file mount, write through
the existing file. Renaming a mount can fail with `EXDEV` or `EBUSY` even when its
contents are writable. With
`--problem`, trusted scaffold files are copied from the installed problem and
overlaid read-only, as in a real run. The task lists `readonly_workspace_paths`.
For the current ECDSA scaffold these are `POINT_ADD_SDK.md` and
`src/point_add_sdk.rs`. Do not recursively chown or modify them. Smoke includes
`remaining_seconds` and a deadline for child processes, but no live model or
problem service. Copying
excludes `.git`, `.env*`, `.openrsi`, `.venv`, `__pycache__` and `.DS_Store`, and
symlinks are rejected. Directory modes are preserved, so a read/write mount alone
does not guarantee that every process can write. Create needed directories at
runtime and check ownership/modes if creation fails, especially if your wrapper
drops privileges. The generated image wrapper sets `USER root`; smoke still drops
all capabilities and enables `no-new-privileges`.

OpenRSI replaces the image's `ENTRYPOINT`/`CMD` with its launcher and invokes the
manifest's entrypoint as an argument list in `/workspace/repo`, without a login
shell. Dockerfile `ENV` values, including `PATH`, are inherited; the launcher adds
the task variables but does not reset `PATH` or source shell profiles. Install
tools with an explicit Dockerfile `ENV PATH=...`, or use an absolute executable
path. For a missing command, inspect `PATH`, the executable and its interpreter
inside the built image; success in a host shell does not establish image behavior.

Replace `agent.py` with your solver. Install its runtime dependencies in the
Dockerfile. Python 3 and Bash are required for the platform
launcher and Dungeness clients; the solver can use any language.

Use `evaluate` to send the candidate to the trusted evaluator for compilation,
correctness checks and scoring. That service has its own pinned Rust toolchain
and dependencies. Your agent can edit Rust source and call `evaluate` without
Rust installed in its own container, in both local Dungeness and hosted runs.
For optional compilation or additional tests inside the agent container, install
the workspace's pinned Rust version (currently 1.93.0) and dependencies during
the Docker build. Runtime internet downloads are unavailable.

The launcher reports agent-side compiler availability in `local_toolchain` and
the task instructions before starting your harness. A missing or mismatched
compiler does not block `evaluate`. This check does not certify dependencies or
prove that a candidate compiles.
The starter copies the whole bundle into `/opt/harness/`, so general-purpose
prompts and helper modules travel with the agent. Use the
[configuration reference](generic-harnesses.md)
to choose provider, model and budget separately from those source files.

Executable packages cannot select a host agent or Python adapter. Package
general-purpose tools and retrieval code in any layout your agent supports.
Problem-specific knowledge belongs to the trusted task: its library endpoint
provides eight bundled papers, and your agent chooses how to read or index them during
the run. `OPENRSI_KNOWLEDGE_BASE_URL` points to the catalog. Do not submit ECDSA
papers, strategies, notes, solution code or answer caches. See the
[screening policy](source-limits.md).

`OPENRSI_TASK` points to a JSON file containing problem/harness references,
instruction, writable workspace, candidate paths, budget, model and gateway
URL, plus an allowed `models` list. `OPENRSI_WORKSPACE`, `OPENRSI_MODEL`
and `OPENRSI_MODELS` are convenience variables.
With the [problem-service runtime](generic-harnesses.md), the launcher first fetches
the server-assigned statement and checks its SHA-256, problem identity and
candidate paths. The resolved task includes `problem_document`, and
`OPENRSI_PROBLEM_URL` points to the read-only document. A failed or mismatched
fetch stops the launcher before your entrypoint runs.
During Dungeness execution, `OPENAI_BASE_URL` points at the metered gateway
and `OPENAI_API_KEY` is only the public placeholder `testbed`. Smoke tests
supply no gateway or model.

Write candidate files under the workspace and exit zero on success. The
independent verifier judges the candidate; submitted stdout or claimed scores
never establish official observations. Never put provider credentials in
source or images.

## Workspace filesystem contract

Snapshotting, branching, search in parallel work directories, and restoring the
best candidate are supported harness designs. Writable does not mean that every
filesystem operation is supported: candidate paths may be separate Docker bind
mounts, and trusted scaffold files are protected.

| Operation | Supported approach |
| --- | --- |
| Edit a candidate directory | Create, update and remove ordinary files inside it. |
| Save a checkpoint | Copy candidate contents to a separate writable work directory. |
| Restore a checkpoint | Copy the saved contents back into the existing candidate directory; remove obsolete ordinary files and verify the restored contents. |
| Replace the whole candidate root with a rename or directory swap | Do not rely on this: a mount root cannot be renamed or replaced. Keep the root in place. |
| Update a candidate that is itself a file mount | Write to the existing file; replacing its inode with a temporary-file rename can fail. |
| Atomic file replacement | Works for ordinary writable files within the same filesystem, not across mount boundaries or over a mounted file. |
| Change trusted scaffold files | Unsupported; preserve the assigned read-only files and their ownership. |

Use the task's `candidate_paths` to locate outputs. Finish restoring a candidate
before requesting evaluation, and stop background writers while restoring it.
A directory restore is not an atomic transaction; retain the checkpoint so it
can be retried after interruption. Test save and restore against an actual bind
mount as well as an ordinary temporary directory. Packaging smoke tests do not
reproduce every live mount boundary.

`EXDEV` ("Invalid cross-device link") can mean a rename crosses filesystem
boundaries; `EBUSY` can mean the target is a mount root. Check the failed operation
and its paths. These are filesystem compatibility errors, not cheating or
security-policy verdicts, and do not make the harness architecture ineligible.
