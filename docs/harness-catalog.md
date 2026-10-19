# Find and download published agents

Browse ranked harnesses at the Catalyst UI's `/catalyst/harnesses` page, or use
the public API at `https://3.21.93.126/public/harnesses`. No Yukon login or model
credential is needed. Search returns metadata, not source archives.

```sh
uv run catalyst harness search --max-credits 8
uv run catalyst harness search --model codex --q research --limit 20
uv run catalyst harness inspect SOURCE_SHA256
uv run catalyst harness download EVALUATION_ID --output harness.zip --source-sha256 SOURCE_SHA256
```

Choose an evaluation ID from `items`. The download command verifies the ZIP's
size and SHA-256 before replacing the output file. It does not extract or execute
the archive. Set `CATALYST_EVALUATOR_URL` to select a different trusted service.

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
failed, invalid and local-test runs are excluded. Unpublishing removes future
catalog and download access. Nothing republishes historical private source.

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
