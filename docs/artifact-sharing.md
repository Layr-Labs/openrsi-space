# Artifact downloads and publication

Remote runs are private by default. Scores published to Yukon do not grant
access to harness source or recorded model/tool output.

Use your existing Yukon dev login and `CATALYST_EVALUATOR_URL`. These commands
operate on a completed evaluation; none starts another model run.

```sh
catalyst remote artifacts EVALUATION_ID
catalyst remote download EVALUATION_ID --kind complete --output complete.zip
catalyst remote download EVALUATION_ID --kind harness --output harness.zip
catalyst remote download EVALUATION_ID --kind traces --output traces.zip
```

Downloads work from another machine with the same solver account; the original
local submission/session file is not required. Files are streamed, checksummed,
saved with private permissions, and never automatically unpacked or executed.
The old `remote traces` command and automatic `--wait` download keep their
smaller diagnostic ZIP for compatibility. Use `remote download` for full evidence.

The harness ZIP is the original submitted source archive, including its
`catalyst-snapshot.json` file hashes. It is not rebuilt from a later checkout.
The complete bundle adds the source ZIP, model/budget configuration without the
private grant reference, problem/pricing/policy pins, final candidate, verifier
reports, usage, Dungeness record and event log, and recorded Codex output.

`artifact-manifest.json` hashes every exported file. `coverage.json` lists
missing evidence and intentional exclusions. Failed runs can have missing
runtime evidence. Container images, dependency caches, arbitrary workspace
files, credential files and unrecorded model internals are not included.
The export fails visibly rather than silently truncating files above 64 MiB
or bundles above 512 MiB / 10,000 files. These are current MVP limits.

Text evidence is sanitized for recognized credentials, bearer tokens, JWTs and
private keys. JSON/JSONL structure is preserved. Export hashes refer to the
sanitized bytes; source-bundle hashes identify the original evaluated source.
Sanitization is best effort: arbitrary research data, code and unusual secrets
can still appear in transcripts. Review before publication.

## Separate opt-in publication

Publishing harness source and publishing traces are independent choices:

```sh
catalyst remote publish EVALUATION_ID --harness --license MIT

# First download and inspect the sanitized trace bundle, then:
catalyst remote publish EVALUATION_ID --traces --confirm-traces-reviewed

catalyst remote sharing EVALUATION_ID
```

Supported source license identifiers: MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause,
GPL-3.0-only, GPL-3.0-or-later, AGPL-3.0-only, MPL-2.0, CC0-1.0, CC-BY-4.0.
Choose only a license you have authority to grant. It applies to your authored
contribution; existing third-party licenses and attribution notices remain in
force. A publication's license cannot be changed retroactively.

The response includes a stable public download page and JSON manifest. Anyone
with these links can read the published material without authentication.
The Catalyst challenge UI's **Source & traces** disclosure reads this public
manifest on demand and binds it to the evaluation ID and source hash in Yukon's
official score metrics. The UI code is maintained in the isolated Yukon
checkout; see [UI setup and hosting](challenge-ui.md). Publishing artifacts
does not require resubmitting scores to Yukon.
The complete private bundle is never published by these switches. However,
traces can contain source snippets, tool inputs and outputs, so separate switches
do not guarantee that sharing traces reveals no harness code.

```sh
catalyst remote unpublish EVALUATION_ID --harness
catalyst remote unpublish EVALUATION_ID --traces
```

Unpublishing stops new public access through Catalyst. It cannot revoke an
already downloaded copy or retract an open-source license. Previously issued
S3 download links expire within five minutes. No source or trace publication
occurs when deploying this feature or migrating an existing run.

## Storage and operator migration

The default local backend places immutable, content-addressed ZIPs beneath
`SERVICE_STATE/artifact-objects/`. The run's export manifest records their
digests; sharing choices live in `artifact_publications` in `jobs.sqlite`.
Existing evidence and the original diagnostic ZIP are retained.

The S3 backend keeps the bucket private, writes encrypted objects, and uses
conditional content-addressed uploads. It issues five-minute signed GET URLs
only after an owner-access or explicit-publication check. Solver credentials
are never forwarded to S3. Public download pages remain stable and point to
the current download endpoint rather than storing an expiring signed URL.
Local copies remain as a recovery cache; this version does not automatically
delete historical evidence.

Provision a dedicated bucket using
[`infra/artifact-storage.yaml`](../infra/artifact-storage.yaml), install the SDK
with `uv sync --frozen --extra s3`, and give the service's IAM role the template's
scoped read/write policy. Use an IAM instance role rather than saving AWS keys in
worker configuration or submissions.

Create `SERVICE_STATE/artifact-storage.json`:

```json
{
  "backend": "s3",
  "bucket": "YOUR_DEDICATED_BUCKET",
  "region": "us-west-2",
  "prefix": "catalyst",
  "run_roots": ["/var/lib/catalyst/evaluator/worker"]
}
```

For the existing VM, `SERVICE_STATE` is `/var/lib/catalyst/evaluator/service`.
No bucket credentials belong in that JSON. Local-only installations may omit
the file; custom worker layouts can set `run_roots` with `"backend": "local"`.
Only the operator controls this file.

Export an existing run or migrate all stopped runs after enabling S3:

```sh
catalyst --state SERVICE_STATE artifact-sync EVALUATION_ID
catalyst --state SERVICE_STATE artifact-sync
```

This does not rerun inference or verification and preserves existing scores and
receipts. It retries failed storage uploads using the same object hashes.
New completed and failed jobs attempt export automatically; an export/storage
failure does not change the evaluation's judgment. It is recorded separately
and retried by an owner download or operator sync.

Back up the queue/database and export manifests in addition to S3 objects:
objects alone do not reconstruct account ownership or publication choices.
S3 versioning is enabled; no automatic retention/deletion policy is installed.
CloudFront can be added later if public-download traffic warrants it. GitHub
or the future static score index should store small metadata and stable public
artifact links, not large trace archives.
