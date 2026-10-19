# Artifact downloads and publication

New remote submissions publish their evaluated harness source by default after the
run stops and publication screening passes. Traces are retained internally for verification and debugging and cannot be
downloaded or published, including by the run owner. Historical private runs remain private.

Use `catalyst remote submit HARNESS_DIR --private-harness ...` to keep source
private. The CLI announces visibility before reading a model credential. Review
source, prompts, assets and third-party rights before submitting. The solver is
responsible for permission to publish those files. Possible credentials block
source publication even when public visibility was requested.

Public visibility does not assign a license. Optionally pass `--source-license MIT`
(or another supported license) when submitting. If omitted, the public page says
that no additional license is granted; bundled licenses still apply.

## Download harness source or change its visibility

```sh
catalyst remote download EVALUATION_ID --kind harness --output harness.zip
# Inspect every file in harness.zip before confirming:
catalyst remote publish EVALUATION_ID --harness --license MIT --confirm-source-reviewed

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
source ZIP. The public download page lists
only publicly available files, with their license information, size and checksum.

**Download and use shared files at your own risk.** They are untrusted code and
content. Inspect source, prompts and dependencies before use, and run code in an
isolated environment. Verification and credential screening do not guarantee
safe code. A SHA-256 checksum confirms that a download matches the published
file; it does not certify safety.

The Catalyst challenge UI's **Harness source** disclosure reads this public
manifest on demand and binds it to the evaluation ID and source hash in Yukon's
official score metrics. The UI code is maintained in Yukon's
`apps/challenges-ui/challenges/catalyst`; see [UI setup and hosting](challenge-ui.md). Publishing artifacts
does not require resubmitting scores to Yukon.
Trace and complete-bundle download endpoints are disabled, including for
historical runs that previously enabled trace sharing. Internal evidence remains
available to operators for verification and debugging.

```sh
catalyst remote unpublish EVALUATION_ID --harness
```

Unpublishing stops new public access through Catalyst. It cannot revoke an
already downloaded copy or retract an open-source license. Previously issued
S3 download links expire within five minutes. No retrospective source publication
occurs when deploying this feature or migrating an existing run.

## Storage

The service retains evidence in operator-managed storage. Changing storage does not change evaluation IDs or owner permissions. Storage backends and migration tools are maintained in the private `catalyst-verifier` repository.
