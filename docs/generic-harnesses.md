# Runtime and gateway reference

For setup, start with [Local setup](local-evaluation.md); for image and entrypoint requirements, use [Build a harness](executable-harness.md).

An `evaluation.json` is optional when all three model/budget flags are provided.
Without a file, the defaults are temporary model access, no token ceiling,
and 10,800 seconds (3 hours). Set an optional ceiling with `--max-tokens`; use
`--no-token-limit` to remove one from a manifest and `--max-seconds` to set the timeout.
With an existing file, flags override its run settings without editing it.
Set provider and model together; switching them clears any inherited reasoning
effort unless `--reasoning-effort` is also given. For ensembles, keep the full
v4 model list in `evaluation.json`; budget and limit flags still apply.

## Execution contract

### Versioned problem and knowledge-base endpoints

New ECDSA problem packages carry the human-readable release `v1` and slug
`ecdsa-fail`. Inside a run, the read-only gateway serves:

| URL path on `http://gateway:8080` | Response |
| --- | --- |
| `/ecdsa-fail/v1/description` | JSON statement, release, content hash, evaluation contract and library link |
| `/ecdsa-fail/v1/knowledge-base` | JSON catalog with a `resources` array |
| `/ecdsa-fail/v1/resources/<resource-id>` | Original resource bytes with their declared `Content-Type` |

Release `v1` contains the pinned eight-paper library. The experimental single-paper
`v0` release is retired and cannot be selected for new runs. Retained results
keep their original problem identities.

The corresponding unversioned paths (`/ecdsa-fail/description`,
`/ecdsa-fail/knowledge-base`, and `/ecdsa-fail/resources/<resource-id>`) resolve
only to this run's assigned release. They do not follow a mutable global
"latest" release. Other releases and unknown resource IDs return 404.
These are internal per-run endpoints, not public website URLs.

Use `OPENRSI_DESCRIPTION_URL`, `OPENRSI_PROBLEM_RELEASE`, and
`OPENRSI_KNOWLEDGE_BASE_URL` instead of hard-coding paths. The description has
`problem_id`, `release`, and `content_sha256`; the latter is the immutable
problem-package hash, covering the statement, execution configuration and pinned
library binding. It is separate from `X-Task-SHA256`, which covers the full
run-specific `/task` response. The description itself excludes the run ID and
has its own `X-Content-SHA256` response header.

Each resource has a stable `id`, `title`, `kind`, `media_type`, `filename`,
`bytes`, `sha256`, and versioned `url`. IDs do not require filename extensions.
Resources may be papers, notes, datasets, code or other material; consumers must
use the catalog's media type rather than assume PDF. Original paper attribution
and license metadata remain in the entries. Resources are verified against
their pinned size and hash before delivery, and downloads include
`X-Content-SHA256`, `Content-Disposition` and `X-Content-Type-Options: nosniff`.

Existing `/task`, `/task/files/knowledge-base.json` (the original `papers`
catalog), and `/task/files/<filename>` URLs remain available. The task envelope
keeps its existing `problem.id` and `problem.version` fields and adds `slug`,
`release` and `description_url`. Existing immutable packages without a release
retain their original endpoints.

Never change the contents associated with a published release tag. Changes to
the problem instructions, supplied resources or execution contract require a
new tag and content hashes. This release is independent of the scoring-policy
version and the JSON `schema_version`. Keep historical packages and receipts;
an existing run is never relabeled as a new release.

A Dungeness command agent uses an ordinary Dockerfile and:

```yaml
execution_mode: installed
execution:
  interface: dungeness-command-v1
  entrypoint: ["python3", "/opt/harness/agent.py"]
```

The image needs Python 3 for the trusted launcher; the harness itself can use
any installed language. Command descriptors cannot select `harbor.import_path`.

Models belong to the run's `model_access.models` list, independently of the
agent. Each profile identifies the provider, request model, API protocol and
pinned pricing identity. The compiler gives the harness a `DUNGENESS_TASK`
JSON file containing the problem instruction, writable workspace, model
endpoints and execution configuration. Real credentials are not in this file.
Research strategy and feedback loops belong to the harness.

One Harbor trial may run many harness subprocesses. They share the run's
compute envelope, gateway and budget. The launcher forwards termination and
kills remaining process-group children on exit. Container teardown remains
the boundary for processes that deliberately detach themselves.
An optional `execution.resume_entrypoint` supports explicit exit-code-75
continuations under `runtime.continuation` limits. It reuses the same sandbox;
this is not durable recovery after host failure.

OpenRSI's existing `openrsi-exec-v1` source interface remains available.
Its wrapper now uses the Dungeness command adapter. `OPENRSI_TASK` also
contains `models`, and `OPENRSI_MODELS` exposes that list as JSON.
The old Codex identity and Dockerfile marker workaround are removed.

## Models and credentials

Read [harness/provider compatibility](harness-compatibility.md) when creating or
adapting a harness. Selecting a model and credential does not translate a
framework's API format. Test every model client, including title and compaction
helpers, against the chosen provider's supported operations and tool schemas.

Existing `evaluation.json` v3 files select one model. Version 4 additionally
requires `models`, with the default `model` first:

```json
{
  "schema_version": 4,
  "llm_access": {"grant_id": "grant_temporary_provider"},
  "model": {"provider": "openai", "name": "gpt-5.6-sol"},
  "models": [
    {"provider": "openai", "name": "gpt-5.6-sol"},
    {"provider": "openai", "name": "gpt-6-astra"}
  ],
  "max_model_credits": 3,
  "limits": {"max_model_tokens": null, "max_seconds": 10800}
}
```

The service must establish pricing for every model. The operator must allow **every** selected provider.
Existing service policy is not expanded automatically.
Every nonzero token bucket must also be priced: configurations that report
cache-write tokens for a model without a pinned cache-write rate fail closed.
Such clients must disable cache writes or wait for a versioned pricing update.

## Reference prices for declared models

Existing entries retain the immutable comparison rates in `pricing.json`.
For a model absent from those entries, the client first calls the authenticated
`POST /pricing/quote` endpoint with its declared models, without sending model
credentials. The service fetches the fixed
[OpenRouter models catalog](https://openrouter.ai/docs/api/api-reference/models/get-models).
New OpenRouter model IDs resolve directly; direct OpenAI, ChatGPT and Anthropic
names resolve under their corresponding catalog author. Ambiguous or unmatched identities fail before inference.
Subscriptions with opaque aliases need a verifiable identity mapping; callers
cannot assign an arbitrary cheaper reference model.

The server stores each quote by content hash. It includes selected rates,
catalog provenance and hash, the issue/expiry times and the normalization policy.
New quotes expire after one hour; accepted jobs retain their original snapshot.
The client retains the quote and operation key through uncertain responses.
It obtains a fresh quote automatically only after the service explicitly
confirms that an expired operation was never accepted. Existing receipts remain
verifiable after expiry or catalog changes.

Catalog prices are converted from dollars per token to reference credits per
million tokens. Missing cache rates use the input rate, as an explicit
normalization rule. Quotes support one prompt-length tier, applied strictly above
the declared input-token threshold (including cached input). Rates are reference
credits, not a claim about subscription consumption. A listed optional web-search
price is excluded only on inference-only routes; OpenRouter also requires the
operator to disable account-default plugins. Listed image, audio and input-audio-cache
prices are excluded because these quotes enforce text-only requests. Nonzero
`internal_reasoning` prices must equal the completion rate at every pricing tier:
reasoning tokens are already included in output usage and are charged once.
Different reasoning rates and other unknown nonzero charges are rejected, as are
paid provider tools, multimodal requests and model fallbacks. Agent-executed function tools remain
available. The service never accepts solver-authored prices or upstream URLs.

For local OpenRouter runs, disable default plugins and hosted server tools in the
workspace owning your key, then set `TESTBED_OPENROUTER_INFERENCE_ONLY=1` in the
environment of `openrsi-space local run`. This explicitly confirms that configuration;
it does not change your OpenRouter settings. The local CLI forwards the assertion
to the trusted gateway. Normal harness-executed function calls still work, including
shell commands and file edits inside Dungeness. Hosted evaluations use the
operator's confirmation for the platform account.

Accepted runs retain their original pricing snapshot, even if the catalog
changes later. The same recorded schedule is used for the run's model-credit
comparison. Quotes and raw usage do not authorize a solver to edit prices.

Personal model credentials stay on the solver's machine for local testing.
Remote runs use platform-funded OpenRouter; do not upload a personal API key
or subscription login. The trusted gateway supplies model access on each route.
The harness uses the
`testbed` placeholder, never native authentication files. Protocol conversion
belongs in the submitted harness. For streamed chat requests, the gateway
requests the final usage chunk and drains it even if the agent disconnects.

## Parallel accounting and evaluation

The gateway authorizes provider/model pairs before contacting the provider.
All admitted requests share one ledger and a bounded number of active slots.
Credits are reserved until the upstream response has drained and settled;
client disconnection does not release the reservation prematurely.
Local and remote runs use the same conservative request reservation policy.
An omitted output limit defaults to at most 16,384 tokens and is reduced to fit
remaining credits. Explicit output limits are honored or rejected. Large
histories can still require more reserved credits than their eventual cached
bill. A reservation rejection reports available and required credits and means
that request did not reach the provider. Shorten history or lower an explicit
output limit before retrying.
Missing usage blocks further admissions. Explicit HTTP 400 input-validation
errors with an `invalid_request_error` body settle at zero tokens. The rejection
basis is retained in the ledger. HTTP 422 responses are not automatically free.
Successful responses without usage,
interrupted streams, and ambiguous errors still block further inference.
OpenRSI prices each settled receipt using that receipt's authorized model,
then checks the terminal total.

Reservations limit concurrent admission; they are **not a hard provider billing
cap**. Actual usage can exceed an allowance, especially with subscription
protocols that lack enforceable per-call cost limits. The gateway then blocks
new calls. Under validity policy v3, OpenRSI accepts in-flight overshoot only
with trusted evidence that every charged request started below the cap. No cost is
clipped to make a result eligible. Use provider-side spending limits where
available. Strict pre-call cost guarantees remain future work.

`evaluate --json PATH` submits a file or directory snapshot and prints the
trusted evaluator's structured response. For the pinned ECDSA directory
interface this includes score, validity, candidate/source digests, evaluation
ID and run ID. Concurrent harness workers may submit different candidate
directories; the trusted ECDSA sidecar serializes verification to protect its
build workspace. Parallel verifier capacity is not implemented.

The existing history exporter accounts conservatively for calls in flight
when an evaluator observation arrives. The full cost/performance curve and
$10/$20/$50/$100/Best views are preserved.

## Example and verification

Your harness may launch parallel model workers or combine multiple models.
Declare every model in the run configuration and send all inference through
its assigned gateway endpoints. Shared usage counts against the run's cap;
parallelism does not grant each worker a separate budget.

## Framework integration and runtime check

Your Dockerfile and entrypoint own the framework setup. Dungeness runs the
submitted command; it does not install or select a bundled coding agent.
Package tools and dependencies before execution because research-time internet
access is disabled.

Use [local build and smoke checks](local-evaluation.md), then submit a funded run
through the remote service when authorized.

## Optional token ceiling

New runs default to credit and time limits without a token ceiling. In
`evaluation.json`, omit `limits.max_model_tokens` or set it to `null`.
Use `--no-token-limit` with `openrsi-space remote submit` or `openrsi-space local run`
to remove a ceiling from an existing manifest. A positive `--max-tokens N`
still enables an explicit ceiling. Token usage is recorded in all cases.
An operator who explicitly requires a finite token ceiling can reject uncapped
requests; the hosted OpenRSI service does not impose one by default.

Build dependencies: run `openrsi-space remote build-policy` before choosing hosted
package sources; see [build dependency policy](source-limits.md#dependency-downloads-during-builds).

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
