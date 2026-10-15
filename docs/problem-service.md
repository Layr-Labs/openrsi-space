# Per-run problem service

Catalyst owns the public problem statement. The verification service assigns a
specific, immutable problem package before executing a submitted harness.
Dungeness supplies generic Compose wiring and model accounting.

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
- `evaluation.command`, currently `evaluate`.

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

## Versions and rollout

Service initialization reads Catalyst's packaged statement, not Dungeness's
historical task text. Each run retains its problem snapshot and generated service
document, with the document digest in its run metadata.

The public ECDSA baseline pin and existing receipt protocol are unchanged.
The ECDSA verifier/task adapters still use the pinned Dungeness definitions;
statement ownership does not replace those executable adapters.

Deploying this requires updated public and private packages plus a clean, pinned
Dungeness revision with problem-service support. The private adapter refuses an
older runtime. Existing service directories are not overwritten automatically;
an operator must deliberately migrate their problem package before new runs use
the revised statement. Retain old snapshots and receipts.
