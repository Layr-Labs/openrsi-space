# Platform-funded inference

When enabled by the operator, OpenRSI supplies its own API access for remote
runs. You supply no personal model credential. Yukon authentication still
identifies your account, and platform allowances determine admission.

```sh
catalyst remote funding-policy
catalyst remote submit ./my-harness --platform-funded \
  --provider openai --model EXACT_MODEL_ID --budget 3 --local-run /path/to/local/run.json
catalyst remote funding
```

Before preparing either run, check that `funding-policy` reports funding enabled.
Check source size with `catalyst remote limits ./my-harness`: both the public ZIP
and expanded source default to **8 MiB**. The private evidence limit below is
separate and does not increase the source limit.

You choose the exact model ID on a funded provider reported by `funding-policy`
(for example, `openrouter` with an exact `author/model` ID). The service validates
and pins its pricing; unknown models, automatic model routing and unsupported
charges are rejected before a run starts. Pair your harness with that API format.
The provider, exact model and reasoning settings must be identical in your local
Dungeness evidence and remote request. Changing any of them requires matching
evidence for the new configuration. Existing operator-restricted deployments may
also report a `models` list; respect it when present. Keep using the assigned gateway and placeholder
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
The exported bundle allows at most 1,000 model calls and 192 MiB.
A configured local spending cap is not enough: only settled actual usage counts.
If the record falls short, lower the remote cap or authorize further local testing;
the CLI never starts additional paid calls to satisfy the requirement. The server
rejects `--skip-local-check` unless the operator has granted an expiring exemption.

The default allowance is 20 model credits (USD equivalent) per authenticated Yukon account
per rolling 24 hours. Changing Yukon keys does not reset it. The operator may
adjust an account's allowance by its authenticated Yukon account ID. Each account may
have one funded evaluation running at a time. You can split the daily allowance
across multiple sequential runs; it is not a one-run-per-day limit. Each run
reserves its requested cap and returns unused funds after settled usage is known.
Separate limits apply to
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

For OpenRouter, local evidence spending and funded settlement use the provider's
reported request charges (`billed_usd`), not the pinned-price estimate. The same
Dungeness gateway accounting is used locally and remotely. The gateway records
`normalized_usd` separately for benchmark comparison and retains that existing
credit ceiling as an additional conservative limit. Other providers retain their
existing normalized accounting. Neither cap can prevent an already in-flight
request from exceeding its reservation; unresolved charges retain their hold. Platform funding may require account enrollment. If it is disabled,
submitting this mode returns an actionable error without starting a run.
