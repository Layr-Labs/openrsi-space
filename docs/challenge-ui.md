# OpenRSI challenge UI

The hosted board lives in `Layr-Labs/yukon` under
`apps/challenges-ui/challenges/openrsi`, with routes at
`apps/challenges-ui/app/(challenge)/openrsi`. The public solver command remains
`openrsi-space`. Older `/catalyst` website links redirect to `/openrsi`.
UI development and deployment belong in Yukon; this package has no separate viewer.

## Local preview

From a Yukon checkout, follow its repository instructions and run:

```sh
NEXT_PUBLIC_API_URL=https://api-dev.yukon.org \
NEXT_PUBLIC_OPENRSI_BENCHMARK_REF=bd33c240-a4b3-4671-ad88-84b847859293 \
NEXT_PUBLIC_LIVE_CHALLENGES=openrsi \
OPENRSI_EVALUATOR_URL=https://3.21.93.126 \
bun run dev:challenges
```

Open <http://localhost:3000/openrsi>. These values select the **dev** environment;
do not copy the dev benchmark or authentication settings into production.
Reading the board starts no evaluation. Sign-in needs the matching environment's
Supabase configuration; public artifact reads do not need a model credential.
`OPENRSI_EVALUATOR_URL` is server-only. Keep secrets out of public environment
variables. Preserve other enabled challenges when changing a shared deployment.

## User-facing workflow

How it works introduces building a general-purpose harness, local Dungeness
execution, official evaluation and receipt publication. Participate provides the
human commands and copied coding-agent instructions. Architecture explains the
runtime boundaries. Keep these consistent with the [solver guide](solver-guide.md)
and [funding requirements](platform-funded-inference.md):

- Public source ZIP and expanded files each default to 8 MiB; use live limits.
- When enabled, funded remote submissions require a matching private local-run
  bundle whose recorded local budget cap covers the remote cap; actual spending may be lower.
- Local tests use the solver's authorized model access. Funded remote runs use
  platform API access and transfer no personal model credential.
- Each account may have one funded evaluation running at a time. Backend fleet
  capacity is an operator detail, not a participation instruction.
- Local evidence is readiness input, not an official score or replay proof. The
  remote run starts fresh. Only a verified receipt is published to Yukon.

Funding reuses the account ID from Yukon's existing authenticated `/api/me` API.
No Yukon backend change is needed. Deploying UI text alone does not activate funding.

## Results and source

The progress panel combines the performance-versus-credits chart, ranked harness
cards and selected-run details. Submission history remains a separate compact
section. Current and archived problem identities stay distinct; scores and curves
come from Yukon's official result packet, not public notes or client claims.
Share links preserve the selected run. Publishing a receipt never repeats inference.

“About this harness” uses the platform-generated source-review summary when one
is available. The shared summary contract allows up to 250 words and 3000 Unicode
characters, with multiple paragraphs and normalized ordinary whitespace. Summary
generation and repair failures are display metadata failures, not failed evaluations.
Solver-authored notes remain separately attributed. Public harness
source is obtained from the verifier's screened artifact endpoint; local evidence,
private traces and generated circuits are not public downloads.

The Yukon directory README is authoritative for current UI environment variables,
preview setup, app checks and release procedures. Publish corresponding OpenRSI
guides before enabling links to them in a hosted UI. Legal pages require separately
approved terms and privacy text; a code deployment does not constitute legal review.
