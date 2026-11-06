# Verifier endpoint

Production uses **https://verify.openrsi.space**, with a trusted TLS certificate
and automatic renewal:

```sh
export OPENRSI_EVALUATOR_URL=https://verify.openrsi.space
export YUKON_API_URL=https://api.yukon.org
```

The production benchmark is `bxue-l2/openrsi-space`, UUID
`26d2d34c-9ef8-47e7-97d5-57ff9e28f0b9`, backed by
`https://github.com/Layr-Labs/openrsi-space`. Authenticate with your production
Yukon account. Dev and production account credentials and board IDs are separate.

Development uses `https://3.21.93.126`, `https://api-dev.yukon.org`, and the
`Layr-Labs/openrsi-space-dev` repository. Do not substitute a dev board UUID or
receipt when publishing a production result.

## Receipt validation and recovery

Yukon's GitHub workflow retrieves an existing remote evaluation; it does not
start Dungeness or spend model credits. The root `verification.json` is an
operator-selected production baseline used to check this integration. It records
an unsuccessful completed run, so validation returns `valid: false` and no score;
it is not an accepted solver result or a reference circuit score.

Solvers publish their own service-issued receipt at `submission/verification.json`.
Keep that receipt, the pending publication record and submission note when
recovering from an error. Do not edit a receipt to match a different server,
account, problem or board.

If receipt retrieval or publication fails, follow
[submission recovery](submission-recovery.md). An endpoint or authorization error
does not invalidate the research result or require another paid evaluation.
