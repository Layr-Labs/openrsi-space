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
CATALYST_EVALUATOR_URL=https://35.92.254.142 \
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
- A **Source & traces** disclosure on runs carrying a verified remote evaluation
  ID and source hash. Open it to see owner-published downloads, source license,
  bundle size and SHA-256. Signed-in owners also see the CLI command for their
  complete private download; the website does not receive their CLI credentials.

## Score and artifact reads

Scores and complete performance–cost curves continue to come from the standard
Yukon benchmark-submissions response. Loading the board does not enumerate
GitHub branches or request each evaluation from the verifier.

Artifact metadata is loaded only when a run's disclosure is opened. The browser
uses the same-origin `/api/catalyst/artifacts/EVALUATION_ID` route. That route
contacts only the configured verifier's **public** manifest endpoint, without
forwarding browser cookies, Yukon credentials or authorization headers. It never
contacts an address provided in a submission. The returned evaluation ID and
source hash must match the official result before any download links are shown.

Source and traces can be published independently. A missing public manifest
means no public artifacts are available; an outage produces a retry state and
does not turn a verified score into a failure. Missing historical source
bindings do not get invented links. Each actual download rechecks publication
at the verifier, including after an owner unpublishes a bundle.

`CATALYST_EVALUATOR_URL` is an optional, server-only HTTPS origin. Without it,
the score board still works and artifact browsing reports that it is not
configured. Set it separately for each deployment's intended verifier; no
public/private storage bucket setting or AWS credential belongs in the UI.
The endpoint and links work with today's VM storage and the future S3 backend.
See [artifact sharing](artifact-sharing.md) for owner publication commands.

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
only inside its browser to exercise budget changes and mobile layout. It also
checks lazy artifact reads, separately published source/traces, unpublication,
source mismatches and service outages without publishing any real artifacts.

The October 9 artifact UI checks passed lint, all app typechecks, scaffold/theme
checks and the focused artifact contracts. The full app test command encountered
existing HTTP-listener and remote-font tests blocked by the restricted session.
The full build and browser check also require an unrestricted environment for
font downloads and Chrome startup. These gates must pass before UI publication.

Nothing is deployed by these commands. When ready, review and publish the patch
through Yukon's normal Challenges UI process. Its Vercel project is
`eigen-labs/yukon-challenges-ui`; the intended public route is `/catalyst`.
Configure `NEXT_PUBLIC_LIVE_CHALLENGES` and the benchmark reference for the
intended environment, retaining other live challenge entries. The UUID above
belongs to **dev**; do not silently point production at a dev benchmark.
Confirm the appropriate API base and Supabase redirect allowlist.
For public artifact browsing, also configure `CATALYST_EVALUATOR_URL`.

The existing GitHub App installation and Yukon dev benchmark registration are
complete. The benchmark uses automatic acceptance after verification, so valid
contributions do not require human review for portfolio publication.
Legal pages are explicitly marked
`[LEGAL REVIEW REQUIRED]` until approved text is supplied.
