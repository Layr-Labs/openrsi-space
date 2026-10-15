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
catalyst remote download EVALUATION_ID --kind harness --output harness.zip
# Inspect every file in harness.zip before confirming:
catalyst remote publish EVALUATION_ID --harness --license MIT --confirm-source-reviewed

# First download and inspect the sanitized trace bundle, then:
catalyst remote publish EVALUATION_ID --traces --confirm-traces-reviewed

catalyst remote sharing EVALUATION_ID
```

Supported source license identifiers: MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause,
GPL-3.0-only, GPL-3.0-or-later, AGPL-3.0-only, MPL-2.0, CC0-1.0, CC-BY-4.0.
Choose only a license you have authority to grant. It applies to your authored
contribution; existing third-party licenses and attribution notices remain in
force. A publication's license cannot be changed retroactively.

You are responsible for reviewing the exact downloaded bundle and ensuring that
you may publicly share its code, prompts, knowledge files and third-party material.
Remove proprietary or otherwise private material before submitting a new harness.
The publication command releases the original evaluated bytes; it cannot silently
remove a file from an already evaluated harness.

Catalyst separately screens source publication for possible credentials. A review
confirmation does not waive credential checks or authorize releasing a model
access token. Model access is supplied outside the source package; runtime auth
files and provider grants are excluded from exports. Detected credentials block
source publication. Scanners cannot prove that arbitrary code contains no private
material or encoded secret, so a passed scan does not replace source review.

The response includes a stable public download page and JSON manifest. Anyone
with these links can read the published material without authentication.
An **artifact** is a file retained from a run: for example, the evaluated harness
source ZIP or the separately shared trace ZIP. The public download page lists
only the files the solver chose to share, with their license, size and checksum.

**Download and use shared files at your own risk.** They are untrusted code and
content. Inspect source, prompts and dependencies before use, and run code in an
isolated environment. Verification and credential screening do not guarantee
safe code. A SHA-256 checksum confirms that a download matches the published
file; it does not certify safety.

The Catalyst challenge UI's **Source & traces** disclosure reads this public
manifest on demand and binds it to the evaluation ID and source hash in Yukon's
official score metrics. The UI code is maintained in Yukon's
`apps/challenges-ui/challenges/catalyst`; see [UI setup and hosting](challenge-ui.md). Publishing artifacts
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

## Storage

The service retains evidence in operator-managed storage. Changing storage does not change evaluation IDs or owner permissions. Storage backends and migration tools are maintained in the private `catalyst-verifier` repository.
