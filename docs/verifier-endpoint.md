# Verifier endpoint

The dedicated OpenRSI VM serves **https://3.21.93.126** with a trusted
Let's Encrypt IP certificate and automatic renewal. No third-party hostname
or SSH tunnel is required.

```sh
export OPENRSI_EVALUATOR_URL=https://3.21.93.126
export YUKON_API_URL=https://api-dev.yukon.org
```

Use the existing Yukon dev login. The current benchmark is
`bxue-l2/openrsi-space`, UUID `bd33c240-a4b3-4671-ad88-84b847859293`, in Pareto
mode. Hosting the verifier on the production VM does not change the Yukon
account environment.

Use the endpoint and Yukon environment specified for your board. Receipt
retrieval does not start Dungeness or spend model credits. If an endpoint or board
binding is wrong, retain the receipt and contact support before rerunning research.

## Recover a publication sent to the historical board

The retired board is retained for history. It is not the destination
for new OpenRSI publications. Changing a GitHub remote URL does not change the
Yukon benchmark stored in a checkout.

Keep the original checkout, pending record, receipt and submission note. Clone
`bxue-l2/openrsi-space` into a new directory, then copy the existing receipt,
unchanged, to `submission/verification.json`. Authenticate separately using the
same Yukon solver account that owns the evaluation. Run `yukon setup`, then
`yukon run` to verify the receipt; neither command starts paid research. Publish
using `openrsi-space yukon-submit` and the existing note and attribution.
Check that the returned `benchmark_id` is
`bd33c240-a4b3-4671-ad88-84b847859293`. This creates a new publication on the
correct board while preserving the failed historical submission.

A 403 from binding an old-board job does not invalidate the evaluation: the
verifier authorizes the new board. Do not rewrite receipts, weaken ownership
checks or pay for another evaluation just to recover publication.
