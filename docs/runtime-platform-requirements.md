# Runtime platform requirements

This is the initial implementation direction, not a claim that the current
prototype enforces the remote runtime guarantees. Develop and test on the Mac,
then run the API and harness worker inside the existing VM accessible through
`ssh openclaw`. Reuse that VM across jobs.
The previous cloud/vault architecture image is a historical design artifact;
[the current architecture](architecture.md) supersedes that hosting choice.

## Credentials

Keep renewable device-login credentials, refresh tokens and API keys locally.
Supply temporary provider access to trusted remote execution components through
a private authenticated channel. A managed vault and a reverse proxy are not
required initially. Implement supported providers separately; a reference
pricing entry does not imply a working provider authentication backend.

Preserve the original local credentials during setup, refresh, cancellation,
failures and cleanup. Run-scoped access has its own lifecycle. Do not put secrets
in source packages, Docker build inputs or layers, submission configuration,
PRs, public results, or retained model/tool traces. The harness receives limited
model access and cannot read renewable provider credentials. End that access on
job completion, cancellation or expiry. Unknown usage or lost authentication
stops evaluation; it does not enable an unmetered fallback.

Bind temporary authorization to owner, evaluation, exact provider/model, funded
tier, token/time limits and expiry. The grant reference in `evaluation.json` is
an identifier, not a credential or independent permission to spend. Server-side
identity and grant ownership checks exist for local fixtures; real identity
verification and provider grant issuance remain to implement.

## Execution, accounting and retention

Run submitted source builds and harnesses inside the existing remote VM, using
separate run workspaces/containers from the API and credential processes.
Per-evaluation VM provisioning and destruction are outside the initial MVP.
Verification needs an isolated trusted
workspace containing only the captured allowed ECDSA candidate paths and the
pinned verifier. Builds, harnesses and candidate code are all untrusted. Agent
Compose is unnecessary for the initial implementation.

Enforce the pinned pricing schedule, count all calls and retries with consumed
usage, reserve concurrent request capacity, settle in-flight usage, and atomically
seal checkpoint windows. The result validator checks the resulting records but
cannot establish that a worker actually enforced these properties. See
[tier accounting](tier-accounting.md) for exact eligibility and the still-open
continuous-run proposal.

Keep immutable source/image IDs, verified candidates, every curve point, usage,
private traces and failure details before cleaning up job processes, containers
and temporary workspaces. The remote VM remains running. Infrastructure costs
remain separate from model credits. Subscription usage need not imply a cash
charge. Yukon submission checks an existing evaluation; GitHub never purchases
a replacement run to validate a receipt.

## Tests required before remote launch

Use synthetic providers locally to exercise temporary authentication, renewal,
concurrent budget enforcement, retries, cancellation, checkpoint ordering and
artifact ownership. Test hostile harnesses against the isolation and credential
boundaries, and verify redaction of retained evidence. Then implement and test
the server's Yukon login validation and GitHub OIDC binding to the exact queued
submission. The local contract suite does not replace these runtime tests.
