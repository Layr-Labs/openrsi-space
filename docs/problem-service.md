# Per-run problem service

OpenRSI owns the public problem statement. The verification service assigns a
specific, immutable problem package before executing a submitted harness.
Dungeness supplies generic Compose wiring and model accounting.

The public sources are
[`problem_server.py`](../src/openrsi_space/runtime/problem_server.py) and
[`description.md`](../src/openrsi_space/problem-set/ecdsa-fail/description.md). Keep `problem-set/`:
it contains the challenge manifest, statement and resources. Reference prices
live separately in `src/openrsi_space/pricing/`. The private
verification API starts and manages the per-run service; solvers do not need
another public endpoint or a separate server command.

## Access from a harness

The local or remote run supplies the assigned problem through the task's gateway.
Read `OPENRSI_TASK` and its assigned URLs instead of running your own problem
server or hard-coding an external endpoint. `GET /task` is available inside the
run; it is not a public website API. No model credential is needed to read it.

## Task document

`GET /task` returns:

- `schema_version: 1` and the assigned `run_id`;
- `problem.id` and the content-addressed problem-package `version`;
- the `title` and `statement`;
- the starting `repository` URL and commit;
- `candidate_paths` and the scoring `metric`;
- `initialization.mode`, currently `scaffold` for ECDSA;
- `evaluation.command`, currently `evaluate`.
- `knowledge_base` with the library ID, count and catalog URL;
- `attachments` binding every allowed file name, media type, byte size and SHA-256.

The OpenRSI launcher fetches this document before starting the harness. It
checks the digest, problem identity and candidate paths, prepends the trusted
statement to the run instructions, and writes the resolved `OPENRSI_TASK`.
`problem_document` contains the response; `OPENRSI_PROBLEM_URL` allows subsequent
queries. Existing harnesses that read `OPENRSI_TASK.instruction` continue working.
Unavailable or mismatched task responses stop execution rather than substituting
user-authored instructions. Old run inputs without this service field retain
their original embedded instructions.

Use `evaluate` to check candidates against the assigned problem. Editing a local
statement or claiming a score in stdout cannot change the official requirements.

## Shared paper library

The problem's `execution.knowledge_base` pins the canonical SHA-256 of
[the paper catalog](../src/openrsi_space/problem-set/ecdsa-fail/knowledge-base/v1.json).
Release v1 contains eight content-pinned research papers about quantum elliptic-curve
arithmetic, reversible circuits, synthesis, uncomputation and resource reduction.
All eight unmodified PDFs ship inside the OpenRSI package, with author attribution,
original source links, recorded Creative Commons licenses and SHA-256 checksums.
The required paper is André Schrottenloher's arXiv:2606.02235v1. Preparation verifies
all bundled bytes and needs no external paper downloads. Existing requests and receipts keep their exact original identities.

Inside a run:

```sh
curl -fsS "$OPENRSI_KNOWLEDGE_BASE_URL"
# Example assigned URL: http://gateway:8080/ecdsa-fail/v1/knowledge-base
```

The current JSON catalog has a `resources` array with each entry's internal
`url`, media type, checksum and size. Fetch those URLs and interpret the declared
media type; do not assume resources must always be PDFs. Historical packages may
expose a `papers` array instead. The launcher supplies the assigned catalog URL in
`OPENRSI_TASK` and `OPENRSI_KNOWLEDGE_BASE_URL`. Harnesses choose their own
reading and retrieval strategy during execution.

Normal preparation verifies the eight PDFs bundled in the installed package and
needs no external paper downloads. It can reuse matching files from
`~/.cache/openrsi/papers` (or `OPENRSI_PAPER_CACHE`). If a bundled file is absent,
the compatibility fallback downloads only its catalog-pinned URL and requires an
exact checksum match. A changed or corrupt bundled file fails preparation. Update
the package or restore the exact pinned bytes; do not substitute another edition.
No local Dungeness knowledge-base directory is required.
The assigned library is read-only. Use its catalog URLs, sizes and checksums;
keep generated indexes and notes in the writable workspace.

All runs using this problem version receive the same library. Library changes
require a new catalog pin and therefore a new problem version. Historical runs
retain their original assignments; do not alias their receipts to this version.
Solvers must not bundle problem-specific material in their harnesses.

## Problem versions

Each run retains its assigned statement, scaffold and resource versions. Changes
to these inputs can change the problem identity and starting conditions. Compare
exact versions, and never relabel historical runs or edit their receipts.

Check `openrsi-space problem current` before preparing a new run. If your client
or local evidence does not match, follow [compatibility guidance](deployment-compatibility.md).
A repository update does not change the assignment of an existing run.

## Local development

`openrsi-space local run` uses the same public task assembly and harness adapter as the
remote worker. Docker Compose starts the problem service automatically. Solvers
need the public OpenRSI package and Dungeness, not `openrsi-space-verifier`.
`--prepare-only` materializes the inputs without model access.
Local results are development evidence, not an official score. See
[local runs](local-evaluation.md).
