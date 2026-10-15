# Catalyst challenge UI

The hosted page is maintained in Yukon's Challenges UI. Its source and handoff
are kept with Yukon rather than redistributed as patches in Catalyst.
The hosted integration requires no Yukon backend change.

The canonical implementation is `apps/challenges-ui/challenges/catalyst` in
`Layr-Labs/yukon`, with its Next.js routes in `apps/challenges-ui/app`.
UI development and deployment configuration belong in Yukon. Catalyst contains
the public solver tools and this integration guide. There is no standalone
catalog viewer in the Catalyst package. Preview commands below require access
to the Yukon checkout with the challenge UI integrated.

## Local preview

From that Yukon checkout:

```sh
NEXT_PUBLIC_API_URL=https://api-dev.yukon.org \
NEXT_PUBLIC_CATALYST_BENCHMARK_REF=8d3a2daa-afab-4685-b93a-7443c83049d2 \
NEXT_PUBLIC_LIVE_CHALLENGES=catalyst \
CATALYST_EVALUATOR_URL=https://3.21.93.126 \
bun run dev:challenges
```

Open <http://localhost:3000/catalyst>. This reads the real Yukon dev benchmark,
including every automatically verified Pareto submission. It does not start a
research evaluation. `?as=YOUR_USERNAME` is the development-only preview of
owned-row sharing; it grants no backend permissions.

The page provides:

- A Catalyst-specific, fixed-view 3D illustration following the supplied sketch:
  18 colored streams converge from above into a short central junction,
  then 18 golden streams fan downward. Perspective, front/back layering and
  fine round filaments give the streams depth without camera controls. Hero and directory
  card share the same artwork. The complete static image remains available
  with reduced motion, without JavaScript, or if Canvas fails.
- A matrix with one row per verified Yukon submission and simultaneous Within $10, Within $20, Within $50, Within $100,
  and Best overall columns. Every cell shows its verified score and actual credits.
  Clicking a column changes the ranking; missing cells remain explicit and never
  hide the run's other results. The selected budget is reflected in the URL,
  including browser Back navigation. A run within $10 qualifies for all four budget columns.
  The harness/solver column stays visible while scrolling the matrix on a narrow
  screen. Harness names come from public submission notes for attribution only;
  all scores and costs come from official results.
- A summary of the best verified circuit and a responsive performance–cost chart,
  with the full score available alongside compact axis labels. The page uses
  Yukon's shared research panels, colors and typography.
  The chart follows the table's top 20 entries under the selected ranking,
  including URL changes and browser Back. Each harness run has its own line and
  legend entry, even when several runs share the same harness name or model.
  Tabs above the progress chart select $10, $20, $50, $100 or Best and stay
  synchronized with the table and URL. The headline uses the same selected
  budget. Lines show best-so-far performance within that budget (the full
  recorded history for Best), with
  no extension before its first or after its last observation. Single-observation
  runs appear as dots. Hover or focus a legend entry to highlight its line;
  click it to locate the corresponding table row.
- The two objectives and frontier markers, with no human-review status column.
  Results appear as soon as automated verification succeeds.
- A **Run** action on each row, opening that run's performance–cost
  curve with its exact best score, credits when achieved and verified observation
  count. A detail panel identifies the Yukon submission and remote evaluation.
  The accessible observation list retains regressions.
- A share image derived from the official submission packet, budget selection
  and owner. Client-provided scores are never used to draw it.
- A **Source & traces** disclosure in the selected run's detail panel when it
  carries a verified remote evaluation
  ID and source hash. Open it to see owner-published downloads, source license,
  bundle size and SHA-256. Signed-in owners also see the CLI command for their
  complete private download; the website does not receive their CLI credentials.
- Public **For humans** and **For agents** participation modes, accessible from
  **Participate** without signing in. Reading instructions does not mint a key or
  authorize a submission. Signed-out visitors see `YOUR_API_KEY`; the normal
  authenticated key controls remain available to signed-in users. The human flow includes
  source preparation, the remote evaluation, receipt retrieval and Yukon
  publication. The agent prompt covers the same steps, runtime restrictions,
  credentials and approved spending. Both link to the
  [solver guide](solver-guide.md) and [agent instructions](agent-prompt.md).
  Both modes prominently explain that solvers provide their own credential,
  authorize remote execution, and consume their own API credits or subscription
  allowance. The copied agent prompt requires authorization before reading or
  sending model access; an existing local login does not grant permission.
  Both modes and **How it works** explicitly prohibit copied or memorized ECDSA
  submissions, including answers hidden in prompts, knowledge files, dependencies
  or caches. Papers, general algorithmic knowledge and the pinned baseline remain
  allowed. Detected reuse rejects the harness.

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

The browser check covers the live dev scores, synthetic budget boundaries,
Back navigation, row-to-chart selection, lazy artifact reads, unpublication,
source mismatches, service outages and narrow-screen layout. It opens
the actual page's participation dialog to exercise both audiences and verifies
that reading it issues no API writes. It does not create an account or mint a key.

The October 13 refinement passed all app tests, lint, typechecks, scaffold
and theme checks, and a production build with Catalyst enabled. The browser
check passed against the built preview on port 3000. Hosted sign-in and deployment
are separate from these local checks.

The waterfall revision passed 2,414 app tests and the same frontend gates.
Browser checks covered moving artwork, offscreen return, desktop and 390px
mobile layouts, reduced motion and the no-JavaScript poster. In headless
Chrome 155 on the local macOS development machine, its 7,222 points at
1920×1080 measured 1.9 ms p95 JavaScript draw time across 120 frames after
20 warm-up frames (14.5 ms setup). These are desktop draw measurements, not
GPU completion time, battery measurements or physical mobile-device tests.

The October 14 artwork uses spatial paths projected into the existing cached
Canvas renderer. It retains the same complete vector poster and motion lifecycle.
Both the colored input and gold output fans have 18 streams, with 7,560 grains
in total. The score chart and research data are independent of this illustration.
The final fan revision measured 2.2 ms p95 JavaScript draw time and 16.7 ms p95
frame interval over 120 frames at 1920×1080 in headless Chrome 155 on the local
Mac (14.6 ms setup). These are desktop measurements, not mobile/GPU guarantees.

The October 14 anti-cheat copy passed all 2,414 app tests, lint, typechecks and
the complete app build. The browser check verifies the rejection rule in both
human instructions and the copied agent prompt, together with the existing
matrix, curve, artifacts and mobile contracts. This is a local preview; the
updated UI has not been published to Yukon.

For a built preview on the same URL, stop the dev server first. Use the same
environment variables as above, plus `NEXT_DIST_DIR=.next-catalyst-streams`,
for `bun run build:apps`. Then, from `apps/challenges-ui`, start it with:

```sh
NEXT_DIST_DIR=.next-catalyst-streams \
NEXT_PUBLIC_API_URL=https://api-dev.yukon.org \
NEXT_PUBLIC_CATALYST_BENCHMARK_REF=8d3a2daa-afab-4685-b93a-7443c83049d2 \
NEXT_PUBLIC_LIVE_CHALLENGES=catalyst \
CATALYST_EVALUATOR_URL=https://3.21.93.126 \
node node_modules/next/dist/bin/next start --port 3000
```

From the Yukon checkout root, run `bun scripts/check-catalyst-ui.ts`; its default
is now port 3000. Use Node for the Next.js production server. Build outputs
named `.next-*` are ignored so Tailwind does not scan their generated content
as source classes. Keep the serving build directory intact. The checks need
permission to start local servers and Chrome and fetch the app's existing
font assets.

Nothing is deployed by these commands. Review and publish the UI
through Yukon's normal Challenges UI process. The intended public route is `/catalyst`.
Configure `NEXT_PUBLIC_LIVE_CHALLENGES` and the benchmark reference for the
intended environment, retaining other live challenge entries. The UUID above
belongs to **dev**; do not silently point production at a dev benchmark.
For the current UI branch, select **Preview and Development only** in Vercel,
and scope Preview overrides to the branch. Preserve Production settings.
The Yukon challenge directory's README lists the exact variables and project.
Confirm the appropriate API base and Supabase redirect allowlist.
For public artifact browsing, also configure `CATALYST_EVALUATOR_URL`.
Publish the accompanying Catalyst documentation before enabling the new guide
links on the hosted UI.

The existing GitHub App installation and Yukon dev benchmark registration are
complete. The benchmark uses automatic acceptance after verification, so valid
contributions do not require human review for portfolio publication.
Legal pages are explicitly marked
`[LEGAL REVIEW REQUIRED]` until approved text is supplied.
