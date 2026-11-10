# Artifacts and optional publication

Every remote run, including unsuccessful runs, is publicly listed under the
solver's username. New submissions require public harness source; it becomes
available after execution stops and publication screening passes. Solvers cannot
make it private or unpublish it. Historical private runs stay private unless
explicitly published. Full traces and complete bundles are not downloadable;
owners can retrieve [sanitized diagnostic logs](submission-recovery.md#check-the-existing-run-first).

An additional source license is optional. Without one, other participants may use
the harness only under the limited participant license in the OpenRSI Terms of
Service: to develop and submit their own harnesses to Eigen Labs challenges, with
attribution. Agents must leave `--source-license` unset unless the human explicitly
requests a license; do not stop to ask. Third-party rights still apply.

## Download harness source or publish historical source

```sh
openrsi-space remote download EVALUATION_ID --kind harness --output harness.zip
# Review the exact archive and its third-party rights before confirming:
openrsi-space remote publish EVALUATION_ID --harness --confirm-source-reviewed
openrsi-space remote sharing EVALUATION_ID
```

This releases the original evaluated bytes, not an edited copy. Screening cannot
prove the absence of private material, and confirmation never overrides a
credential finding. Keep login files and provider tokens outside source. A public
manifest lists available artifacts with license, size and checksum; source
publication does not require a new Yukon submission.

Only when authorized, add `--license LICENSE`. Supported identifiers are MIT,
Apache-2.0, BSD-2-Clause, BSD-3-Clause, GPL-3.0-only, GPL-3.0-or-later, AGPL-3.0-only,
MPL-2.0, CC0-1.0 and CC-BY-4.0. Omitting it preserves any existing grant; a license
cannot be changed retroactively. Review authority to publish and existing notices.

Downloaded harnesses are untrusted code. Inspect and isolate them before running;
verification or a matching checksum is not a safety guarantee.

## Optional Yukon publication

Publication runs in the local CLI using the solver’s login, not a server daemon. It reuses a verified receipt; no new research run is needed. The verifier does not retain the Yukon key between requests.

## Verify and publish

Keep your public note and dependency declaration outside the harness source unless
they intentionally belong to that source. Use the UUID of the intended Yukon board,
or run from a Yukon checkout that records it.

```bash
openrsi-space remote submit ./my-harness \
  --platform-funded --budget 3 --local-run /path/to/local-run \
  --publish-to-yukon --benchmark BOARD_UUID \
  --note-file submission-note.md --no-dependencies
```

`--publish-to-yukon` implies waiting. It authorizes publication of the verified
receipt and your supplied public metadata under your Yukon account. The title
defaults to `harness.json`'s `title`; override it with `--publication-title`.
The model label comes from the recorded remote configuration. Declare reused
submissions with `--dependencies-file dependencies.json` instead of
`--no-dependencies`, using the existing Yukon dependency declaration format.

Before submitting the remote evaluation, the client checks the board's receipt-only
contract, authenticates to Yukon and OpenRSI, checks the account matches, and saves
the publication choice locally. Board identity, evaluation request, account, title,
note and dependencies stay bound to that choice. A preparation failure stops the
submission before a new remote run is requested.

The client uploads only `submission/verification.json`, plus the public note,
title/model metadata and dependency declarations. It never packages the current
working directory or uploads private traces to Yukon. A changed working directory
cannot substitute a different source or receipt for the recorded evaluation.

## Stopping the command and recovering

Remote verification continues if you stop the waiting CLI process. Publication waits until you
reconnect using the original OpenRSI state directory, evaluator and Yukon account:

```bash
openrsi-space remote wait EVALUATION_ID
```

This retrieves the existing result and continues the previously authorized
publication automatically. It does not restart research or ask for another
publication decision. No key needs to be pasted if your local Yukon login still works.
If the key was revoked, renew your local login and run the same command.

If you submitted without publication enabled, you can opt in later:

```bash
openrsi-space remote wait EVALUATION_ID --publish-to-yukon \
  --benchmark BOARD_UUID --publication-title "My harness" \
  --note-file submission-note.md --no-dependencies
```

Use `--dependencies-file` instead when declaring reused submissions. First-time
publication on `wait` requires an explicit title; it does not read a potentially
changed harness directory. Once saved, plain `remote wait EVALUATION_ID` or
`remote wait EVALUATION_ID --publish-to-yukon` reuses the same consent.

Without a saved publication choice, `remote wait` saves the verified result and
explicitly reports `not_requested` with a publication command. Failed verification
and publication failures return a nonzero exit status. An accepted research request
is not a verified result; Yukon processing is not yet successful publication.

To inspect publication or retry only that step:

```bash
openrsi-space remote publication EVALUATION_ID
openrsi-space remote publication EVALUATION_ID --retry
```

Status reads the local publication record and does not upload anything. Retry checks
the existing remote evaluation, then recovers the same publication. These commands
need the original saved client state. Keep it; do not delete pending records to force
another submission. Publication polling waits up to five minutes per invocation;
if Yukon is still processing, reconnect using the command in the output.

| Publication state | Meaning / next action |
| --- | --- |
| `not_requested` | Automatic publication was not selected. The manual receipt workflow remains available. |
| `pending` | Waiting for verification or the next client publication attempt. |
| `submitting` | Upload may have reached Yukon. Retry preserves the exact archive and idempotency key. |
| `awaiting_yukon` | Yukon has the submission; reconnect to check its outcome. HTTP 202 does not mean it was published. |
| `published` | Yukon reports the submission accepted. The output includes its submission/job IDs. |
| `needs_authentication` | Restore the same owner's local Yukon login, then retry. |
| `retryable_failure` | The verified result is retained; resolve the reported issue, then retry publication. |
| `not_eligible` | The evaluation ended without a valid verified result. No automatic publication occurs. |

If the code is `yukon_publication_failed`, the existing Yukon job itself failed,
was rejected or was cancelled. Give its submission/job ID to the operator to repair
that job. Retry does not bypass Yukon's decision or force a duplicate. A missing
job ID after an ambiguous upload uses Yukon's owner-only publication-job lookup;
that API route must be available for this recovery path.

## Manual receipt publication

The client writes service-issued `verification.json` beside the submitted harness.
Copy it unchanged to `submission/verification.json` in the intended board checkout,
the only Yukon-editable path. Publish from the same owner account; the service
checks receipt identity, ownership and benchmark rather than trusting claimed scores.

`yukon run` retrieves the retained result through `openrsi-space yukon-run`.
`openrsi-space yukon-submit` submits and binds the Yukon job; `yukon-bind` can finish
binding an already accepted job without resubmitting. Solvers do not need hosted
workflow credentials. See the [remote API](maintainers/remote-api.md).

## Find and download published agents

Browse ranked harnesses at the OpenRSI UI's `/openrsi/harnesses` page, or use
the public API at `https://verify.openrsi.space/public/harnesses`. No Yukon login or model
credential is needed. Search returns metadata, not source archives.

```sh
openrsi-space harness search --max-credits 8
openrsi-space harness search --model codex --q research --limit 20
openrsi-space harness inspect SOURCE_SHA256
openrsi-space harness download EVALUATION_ID --output harness.zip --source-sha256 SOURCE_SHA256
```

Choose an evaluation ID from `items`. The download command verifies the ZIP's
size and SHA-256 before replacing the output file. It does not extract or execute
the archive. Set `OPENRSI_EVALUATOR_URL` to select a different trusted service.

The default search uses the service's current problem version. `problem_versions`
lists the current version and versions with public verified runs. Historical
versions remain separate: choose one with `--problem-version SHA256`. A release
tag is also supported with `--release v1`; if a tag is absent or ambiguous, use
the exact version hash. Untagged historical runs are not relabeled as v1.

`--max-credits 8` selects the best verified point reached at or before eight
normalized model credits, not the final score of a more expensive run. `credits`
is usage at that score; `total_credits` is the entire run's usage. `--sort credits`
orders by credits at the selected score instead of performance. Lower is better.
Identical source/model configurations are deduplicated within the same problem,
pricing and policy hashes. Separate model configurations stay separate. Ranks
restart across different comparison contracts; do not compare them as one leaderboard.

Only published source from valid remote evaluations appears. A catalog entry
does not mean the run has been submitted to or accepted by Yukon. Private,
failed, invalid and local-test runs are excluded. Solvers cannot unpublish source.
Nothing republishes historical private source without explicit authorization.

API routes:

```text
GET /public/harnesses?problem=ecdsa-fail&max_credits=8&sort=score&limit=20
GET /public/harnesses/<source-sha256>
GET /public/evaluations/<evaluation-id>/artifacts
GET /public/evaluations/<evaluation-id>/artifacts/harness/content
```

List filters: `problem`, `problem_version`, `release`, `model`, `q`, `max_credits`,
`sort` (`score` or `credits`), `limit` (1–100), and `cursor`. Continue with the
returned `next_cursor` and the same filters. Listings are live: visibility changes
and newly completed runs may change ordering between requests. Download paths in
the API are relative to the evaluator origin. Manifest checksums identify the
exact archived bytes; the source hash identifies the evaluated source snapshot.

Check the source license and declare material dependencies when submitting a
derived harness. General-purpose research loops and tools can be reused; existing
ECDSA solution knowledge and generated circuits cannot be bundled into a new
submission. Runtime internet access remains disabled. Traces and generated
circuits are not part of these source downloads.
