# Per-run problem service

Catalyst owns the public problem statement. The verification service assigns a
specific, immutable problem package before executing a submitted harness.
Dungeness supplies generic Compose wiring and model accounting.

The public sources are
[`problem_server.py`](../src/catalyst/runtime/problem_server.py) and
[`description.md`](../src/catalyst/problem-set/ecdsa-fail/description.md). Keep `problem-set/`:
it contains the challenge manifest, statement and resources. Reference prices
live separately in `src/catalyst/pricing/`. The private
verification API starts and manages the per-run service; solvers do not need
another public endpoint or a separate server command.

## What runs

The worker builds the harness separately from the problem service. Only trusted
server code generates the problem service's Dockerfile, server and task document;
files with those names inside submitted source cannot replace them.

The Compose `problem` service runs as an unprivileged user with a read-only
filesystem, dropped capabilities, no host ports, and a read-only task-document
mount. Its private Docker network contains only `problem` and `gateway`.
The harness remains on the internal agent network and reaches the document
through `http://gateway:8080/task`.

The gateway uses a fixed internal upstream. It does not accept a problem selector
or client-supplied URL, follow redirects, or forward credentials. It checks the
document against the SHA-256 assigned in trusted Compose configuration.
The problem service has no model credentials and does not execute candidates.

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

The document digest covers the complete response, including the run ID.
It uses UTF-8 JSON with sorted keys, compact separators, non-ASCII characters
preserved, and non-finite numbers rejected.

The Catalyst launcher fetches this document before starting the harness. It
checks the digest, problem identity and candidate paths, prepends the trusted
statement to the run instructions, and writes the resolved `CATALYST_TASK`.
`problem_document` contains the response; `CATALYST_PROBLEM_URL` allows subsequent
queries. Existing harnesses that read `CATALYST_TASK.instruction` continue working.
Unavailable or mismatched task responses stop execution rather than substituting
user-authored instructions. Old run inputs without this service field retain
their original embedded instructions.

The harness may ignore instructions, but it cannot change what the server accepts
as a solution. The trusted evaluator remains a separate service, and final
verification remains independent. This endpoint only serves the problem; it
does not turn the model gateway into a candidate-execution process.

## Shared paper library

The problem's `execution.knowledge_base` pins the canonical SHA-256 of
[the paper catalog](../src/catalyst/problem-set/ecdsa-fail/knowledge-base/v1.json).
Release v1 contains 40 content-pinned research papers about quantum elliptic-curve
arithmetic, reversible circuits, synthesis, uncomputation and resource reduction.
All 40 unmodified PDFs ship inside the Catalyst package, with author attribution,
original source links, recorded Creative Commons licenses and SHA-256 checksums.
The required paper is André Schrottenloher's arXiv:2606.02235v1. Preparation verifies
all bundled bytes and needs no external paper downloads. Existing requests and receipts keep their exact original identities.

Inside a run:

```sh
curl -fsS "$CATALYST_KNOWLEDGE_BASE_URL"
# http://gateway:8080/task/files/knowledge-base.json
```

The JSON `papers` array contains each PDF's internal `url`, checksum and size.
Download from those URLs; agents do not need internet access or a credential.
The launcher exposes the catalog URL in both the resolved task and this environment
variable. Reading is optional: the harness chooses its own retrieval strategy.

Trusted task preparation downloads the pinned files once and verifies every hash.
The default cache is `~/.cache/catalyst/papers`; an operator or local developer can
set `CATALYST_PAPER_CACHE` to another directory. The current library is about 59 MB.
The cache can be seeded with the exact selected PDFs before preparation, including
the original collection's 32 files under their unchanged filenames. No local
Dungeness knowledge-base directory is required at runtime. Missing files are
downloaded from the catalog's arXiv/IACR URLs and accepted only if their bytes
match the pinned checksums. A changed upstream edition stops preparation; the
operator must supply the retained original. No arbitrary URL is accepted.
The immutable copies are mounted read-only in the existing problem service;
there is no separate knowledge-base service. The gateway serves only declared
files, checks their complete hashes before returning content, and never forwards
caller credentials or follows redirects.

All runs using this problem version receive the same library. Library changes
require a new catalog pin and therefore a new problem version. Historical runs
retain their original assignments; do not alias their receipts to this version.
Solvers must not bundle problem-specific material in their harnesses.

## Versions and rollout

Service initialization reads Catalyst's packaged statement, not Dungeness's
historical task text. Each run retains its problem snapshot and generated service
document, with the document digest in its run metadata.

The public ECDSA source commit, scoring rules and receipt protocol are unchanged.
The updated execution configuration changes the problem-package version.
Catalyst also owns the ECDSA execution configuration in `problem-set/ecdsa-fail/releases/v1.json`:
source commit, candidate paths, interface, initialization, resource limits and
verifier selection. The worker generates a task and checkpoint in its private
per-run runtime; it does not look up Dungeness task, problem or checkpoint
manifests. Dungeness still supplies the selected verifier implementation and
generic execution components, pinned by the runtime commit.

The ECDSA default selects `scaffolds/ecdsa-point-add-sdk-v1/scaffold.yaml`.
The runtime removes the upstream candidate and supplies only the ABI stub.
The same pinned neutral SDK and progressive checks are installed in the agent
workspace and trusted evaluators. The scaffold has no reference score.
This changes the starting conditions and therefore the problem version; it
must not be aliased to historical checkpoint-start runs.

Deploying this requires updated public and private packages plus a clean, pinned
Dungeness revision with problem-service support. The private adapter refuses an
older runtime. Existing service directories are not overwritten automatically;
an operator must deliberately migrate their problem package before new runs use
the revised statement. Retain old snapshots and receipts.

Old service packages containing `execution.task` or a checkpoint reference are
rejected before execution, with instructions to initialize a new service package.
Existing retained runs and receipts are not rewritten. A deployment must migrate
the worker package and its published problem set together; historical receipts
keep their original problem-set identity.

## Local development

`catalyst local run` uses the same public task assembly and harness adapter as the
remote worker. Docker Compose starts the problem service automatically. Solvers
need the public Catalyst package and Dungeness, not `catalyst-verifier`.
`--prepare-only` materializes the inputs without model access.
The remote worker adds private operator policies after public preparation; local
results are development evidence. See [local runs](local-evaluation.md).
