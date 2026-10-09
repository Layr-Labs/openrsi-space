# Catalyst challenge UI

The new page is implemented in the isolated stock Yukon checkout
`.catalyst/yukon-publish`, under `apps/challenges-ui/challenges/catalyst` and
`apps/challenges-ui/app/(challenge)/catalyst`.
The original Yukon checkout and backend are not modified by this work.
The reviewable source patch is `integrations/yukon/challenge-ui.patch`;
its base commit is recorded beside it. The integrated source branch is
[`catalyst/verified-harness-ui`](https://github.com/Layr-Labs/yukon/tree/catalyst/verified-harness-ui),
based on current Yukon master and its shared layout.

## Local preview

From the Catalyst directory:

```sh
cd .catalyst/yukon-publish
NEXT_PUBLIC_API_URL=https://api-dev.yukon.org \
NEXT_PUBLIC_CATALYST_BENCHMARK_REF=8d3a2daa-afab-4685-b93a-7443c83049d2 \
NEXT_PUBLIC_LIVE_CHALLENGES=catalyst \
bun run dev:challenges
```

Open <http://localhost:3000/catalyst>. This reads the real Yukon dev benchmark,
including every automatically verified Pareto submission. It does not start a
research evaluation. `?as=bxue-l2` is the existing development-only preview of
owned-row sharing; it grants no backend permissions.

The page provides:

- A matrix with one row per harness run and simultaneous Within $20, Within $200,
  and Best overall columns. Every cell shows its verified score and actual credits.
  Clicking a column changes the ranking; missing cells remain explicit and never
  hide the run's other results. A cheaper run qualifies for both budget columns.
- The two objectives and frontier markers, with no human-review status column.
  Results appear as soon as automated verification succeeds.
- A per-run performance–cost curve and an accessible list of all observations,
  including regressions.
- A share image derived from the official submission packet, budget selection
  and owner. Client-provided scores are never used to draw it.

The full Pareto history is fetched through the standard Yukon API. The default
promoted-only scalar board would omit these results. Legacy final-only receipts
remain usable within their recorded cost; missing early results are not invented.
The already-published test still shows its original $0.887796 pair. Local history
replay does not modify that immutable receipt or Yukon submission.
The newer `198b4e96-827e-48ed-9b8f-3a498db316a2` submission includes six actual
observations, all checked against the remote judgment and rendered in the local
browser. The intentionally fabricated-score submission is excluded.

## Validation and hosting

Run the frontend gates in Yukon's `AGENTS.md`, plus `verify:scaffold`,
`bun test tests/unit/ui-challenges-theme.test.ts` and
`bun scripts/check-catalyst-ui.ts`.
The browser check reads the real dev result, then supplies synthetic history
only inside its browser to exercise budget changes and mobile layout.

Nothing is deployed by these commands. When ready, review and publish the patch
through Yukon's normal Challenges UI process. Its Vercel project is
`eigen-labs/yukon-challenges-ui`; the intended public route is `/catalyst`.
Configure `NEXT_PUBLIC_LIVE_CHALLENGES` and the benchmark reference for the
intended environment, retaining other live challenge entries. The UUID above
belongs to **dev**; do not silently point production at a dev benchmark.
Confirm the appropriate API base and Supabase redirect allowlist.

The existing GitHub App installation and Yukon dev benchmark registration are
complete. The benchmark uses automatic acceptance after verification, so valid
contributions do not require human review for portfolio publication.
Legal pages are explicitly marked
`[LEGAL REVIEW REQUIRED]` until approved text is supplied.
