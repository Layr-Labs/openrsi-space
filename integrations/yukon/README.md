# Yukon challenge integration

## Current contract

The current implementation adds a **direct backend retrieval provider** in
`.catalyst/yukon-remote-service`. Its patch is `remote-verification.patch`, based
on `remote-verification-base-revision.txt`. It uses Yukon's existing Pareto parser
and stores verified result metrics through the normal evaluation path.
See [the deployed VM and integration guide](../../docs/remote-vm.md).

The repository root contains one schema-v1 `benchmark.json`, with shared editable
source under `submission/`. The official problem is **ecdsa.fail** and the model
credit tiers are **$20 and $200, plus Best achieved**.

```sh
yukon setup
yukon run     # remote evaluation, once its service is connected
yukon submit --note-file submission-note.md --model "<exact model>" --harness "<harness>"
```

Use a current Yukon CLI with Pareto support. `yukon setup` downloads the pinned
ECDSA repository without clearing candidate edits or caches; it does not run the
expensive circuit verifier. `yukon run` sends the source snapshot, model, funded
tier, limits and private grant reference to the evaluator using the Yukon login.
The private VM service uses explicitly provisioned account and consumer keys.
The starter grant is blank; no hosted Catalyst benchmark has been registered.

The client retains private traces and writes a v2 `submission/verification.json`.
The new Yukon backend provider authenticates with a dedicated consumer key and
retrieves that existing evaluation, checking ownership, source, image, problem,
configuration, pricing and policies. It does not execute submitted code or start
another evaluation. Its endpoint and credential are deployment configuration,
not editable submission fields. The GitHub workflow remains a legacy adapter.

## Finite score tuples and tier rankings

Yukon's current `src/benchmark/pareto.ts` accepts finite tuples with exactly as
many values as the manifest has objectives. It rejects missing/null tuple
components. `src/benchmark/manifest.ts` also rejects overlapping editable paths
between schema-v2 tracks.

Catalyst therefore keeps one schema-v1 benchmark and two minimizing objectives:
`[best_verified_performance, model_credits_at_that_capture]`. The second coordinate is cumulative credits at the best verified capture.
The run retains an explicit positive finite credit cap and separate total usage. The entire tuple is null for invalid
results. Missing tier measurements stay explicit in metadata; never pad them
with zero, Infinity or a fabricated baseline. Separate tiers must not become
tracks sharing `submission/`.

The actual checkpoint and best-result leaderboard must use the trusted tier summaries in public
metrics. Yukon's generic Pareto order for the two-value transport is not a
substitute. Retain complete verified curves, actual model usage, source/image
identity, exact model, pricing, limits and condition grouping. See
[the tier specification](../../docs/tier-accounting.md) and
[the HTTP contract](../../docs/remote-evaluation.md).

One continuous run with checkpoints remains proposed; the result contract does
not select its scheduling policy or automatically grant lower-tier eligibility.

## Historical board preview

`catalyst-challenge.patch` and `.catalyst/yukon-integration/` preserve the earlier
synthetic multi-problem board preview. Its base is in `base-revision.txt`.
**That preview predates the ECDSA tier contract and is not a launch-ready viewer.**
It still assumes per-problem tracks, arbitrary viewing budgets and median
summaries. It has not been regenerated or deployed in this change.

The preview was scaffolded with the Yukon repository's `create-challenge` skill;
its files live under `apps/challenges-ui/challenges/catalyst/`,
`apps/challenges-ui/app/(challenge)/catalyst/`, and the two
`scripts/catalyst-fixture-api.ts` / `scripts/verify-catalyst-board.ts` fixtures.
Retain this prior work for the future board migration. Do not apply the patch to
a checkout that already contains it, or treat its fixture results as official.

For the updated local viewer now, run from the Catalyst root:

```sh
uv run catalyst demo
uv run catalyst serve
```

Open http://127.0.0.1:8765 and select $20, $200 or Best achieved. The synthetic ECDSA
winner changes with the tier; all curves remain visible. Local evidence remains
synthetic or contributor-reported and cannot qualify for official rankings.

## Remaining launch work

1. Release the tested Yukon provider change and configure the hosted backend's
   secure route and consumer credential for the private `openclaw` service.
2. Add temporary provider access from locally retained renewable credentials,
   concurrent credit reservation/settlement, immutable capture and tier seals.
3. Extend explicit account provisioning to automatic Yukon identity/grant
   issuance. Protected storage and owner/source-bound retrieval are implemented.
4. Migrate the historical board and fixture to ECDSA tier summaries, a single
   source submission benchmark, best-result ranking, complete curves and
   explicit unmeasured tier states. Extend the public solver-profile backend,
   which currently discovers promoted submissions only, for Pareto results.
5. Register the benchmark, obtain an explicitly funded verified starter reference,
   configure its UUID, URLs and live allowlist, and finish legal documents.

No vault, reverse proxy or Agent Compose dependency is required initially.
The Catalyst VM deployment is authorized. Paid model calls, repository commits,
pushes and hosted Yukon releases have not been performed.
