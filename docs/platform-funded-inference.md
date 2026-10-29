# Platform-funded inference

When enabled by the operator, OpenRSI supplies its own API access for remote
runs. You supply no personal model credential. Yukon authentication still
identifies your account, and platform allowances determine admission.

```sh
catalyst remote funding-policy
catalyst remote submit ./my-harness --platform-funded \
  --provider openai --model MODEL_FROM_POLICY --budget 3 --local-run /path/to/local/run.json
catalyst remote funding
```

Before preparing either run, check that `funding-policy` reports funding enabled.
Check source size with `catalyst remote limits ./my-harness`: both the public ZIP
and expanded source default to **8 MiB**. The private evidence limit below is
separate and does not increase the source limit.

Choose an exact API model shown by `funding-policy` and pair your harness with
that provider's API format. Keep using the assigned gateway and placeholder
credentials. Do not include personal model keys or login files in this flow.
`--platform-funded` cannot be combined with credential input flags.

A matching completed local Dungeness test is required for funded runs. Local tests
use your explicitly supplied model access; platform funding applies to admitted
remote runs only. The client uploads recorded model requests/responses/accounting
and evaluation events privately for readiness review. This is separate from public
harness source. Review your logging for secrets and personal information first.
No local login files or arbitrary filesystem archives are included. Logs are
scanned for possible secrets before third-party LLM review.

Use an existing matching record with `--local-run PATH`; the client can also find
records under its state directory automatically. Source, problem, provider, model
and reasoning settings must match. A valid circuit is not required. Recorded settled local spending must be at least
half of the requested remote budget: a 20-credit remote run requires at least
10 credits in the matching local run.
The exported bundle allows at most 1,000 model calls and 64 MiB.
A configured local spending cap is not enough: only settled actual usage counts.
If the record falls short, lower the remote cap or authorize further local testing;
the CLI never starts additional paid calls to satisfy the requirement. The server
rejects `--skip-local-check` unless the operator has granted an expiring exemption.

The default allowance is 20 normalized credits per authenticated GitHub account
per rolling 24 hours. Changing Yukon keys does not reset it. The operator may
adjust an account's allowance by its verified GitHub identity. Each account may
have one funded evaluation running at a time. Separate limits apply to
screening/upload attempts.
A passing review establishes readiness, not authenticity or deterministic replay;
your remote run begins fresh and is the only source of an official score.

A run reserves its budget against your allowance. The platform also reserves
an in-flight buffer from its global pool.
Concurrent runs and retries cannot reuse the same allocation. Screening/build
failures before inference release the reservation. Completed runs settle actual
normalized usage. If usage is uncertain after execution starts, the reservation
remains held until the operator reconciles it. Check `remote funding` for status;
amounts there are microcredits (1,000,000 = one normalized credit).

These benchmark credits are not a provider invoice or guaranteed hard billing
limit. Platform funding may require account enrollment. If it is disabled,
submitting this mode returns an actionable error without starting a run.
