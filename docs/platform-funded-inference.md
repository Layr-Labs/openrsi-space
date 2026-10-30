# Platform-funded inference

## Local access and remote eligibility

| Stage | Model access and payment | Authentication |
| --- | --- | --- |
| Local development | Your existing Codex/ChatGPT or Claude subscription, or a supported API provider; your account supplies the usage | Your authorized local login/key |
| Funded remote evaluation | Eigen Labs pays for OpenRouter calls | Yukon key; no personal model key uploaded |
| Publish a verified result | No new inference | Yukon key and service-issued receipt |

**Does a subscription local run qualify for funded OpenRouter evaluation? Yes,
for supported equivalent models.** For example, local `openai-chatgpt/gpt-6-astra`
qualifies for remote `openrouter/openai/gpt-6-astra`; local
`claude-subscription/claude-opus-5-5` qualifies for remote
`openrouter/anthropic/claude-opus-5.5`. Reasoning settings, harness source and
problem must match. Claude evidence cannot qualify for Astra. The versioned
`local_evidence_models` mapping in `openrsi-space remote funding-policy` lists
accepted pairs. Unlisted pairs still require an exact provider/model match.
The top-level `providers` list describes remote funding only, not local access.
This policy does not translate API requests: the unchanged harness must support
both selected routes using the task-assigned endpoints and model names.

Before spending locally to qualify, run `openrsi-space remote funding-policy` for
supported providers and policy, then `openrsi-space remote funding` for your
reservations and settled usage. Neither command starts inference. Account-specific allowance overrides can be confirmed with the operator;
allowance changes do not waive required local evidence.

Agree on separate local and remote budgets. A **$4 remote cap needs at least $4
in recorded local usage (USD equivalent)**, not merely a configured $4 limit.
Subscription tests consume plan allowance; their settled normalized usage qualifies
without a cash charge. Local OpenRouter runs use provider-reported charges. Leaderboard credits use reference
prices and can differ from actual charges. Do not spend extra to meet the gate
without authorization.

Repository access is separate from both Yukon authentication and model access.
The current repository is `https://github.com/Layr-Labs/openrsi-space` and is
internal; a GitHub 404 may require signing in with organization access. Request
access rather than substituting another repository. `yukon clone layr-labs/catalyst`
is still the correct Yukon registry locator; it is not the GitHub repository name.

When enabled by the operator, OpenRSI supplies its own API access for remote
runs. You supply no personal model credential. Yukon authentication still
identifies your account, and platform allowances determine admission.

```sh
openrsi-space remote funding-policy
openrsi-space remote submit ./my-harness --platform-funded \
  --provider openrouter --model EXACT_AUTHOR/MODEL_ID --budget 3 --local-run /path/to/local/run.json
openrsi-space remote funding
```

Before preparing either run, check that `funding-policy` reports funding enabled.
Check source size with `openrsi-space remote limits ./my-harness`: both the public ZIP
and expanded source default to **8 MiB**. The private evidence limit below is
separate and does not increase the source limit.

You choose the exact model ID on a funded provider reported by `funding-policy`
(for example, `openrouter` with an exact `author/model` ID). The service validates
and pins its pricing; unknown models, automatic model routing and unsupported
charges are rejected before a run starts. Pair your harness with that API format.
The exact model (or a supported provider equivalent) and reasoning settings must
match your local Dungeness evidence. Changed models or efforts require matching
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
records under its state directory automatically. Source, problem, model (or supported provider equivalent)
and reasoning settings must match. A valid circuit is not required. Recorded settled local spending must be at least
the full requested remote budget: a 20-credit remote run requires at least
20 credits in the matching local run.
The exported bundle allows at most 1,000 model calls and 192 MiB.
A configured local spending cap is not enough: only settled actual usage counts.
If the record falls short, lower the remote cap or authorize further local testing;
the CLI never starts additional paid calls to satisfy the requirement. Every new
funded submission requires the bundle; neither solver flags nor operator allowance
overrides can waive it.

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
failures before inference release the reservation. Completed OpenRouter runs settle provider-reported charges. If usage is uncertain after execution starts, the reservation
remains held until the operator reconciles it. Check `remote funding` for status;
amounts there are microcredits (1,000,000 = one USD of OpenRouter funding).

For OpenRouter, local evidence spending and funded settlement use the provider's
reported request charges (`billed_usd`), not the pinned-price estimate. The same
Dungeness gateway accounting is used locally and remotely. The gateway records
`normalized_usd` separately for benchmark comparison and retains that existing
credit ceiling as an additional conservative limit. Other providers retain their
existing normalized accounting. Neither cap can prevent an already in-flight
request from exceeding its reservation; unresolved charges retain their hold. Platform funding may require account enrollment. If it is disabled,
submitting this mode returns an actionable error without starting a run.

`remote funding` includes `allowance` in USD equivalent: the account limit,
usage plus active reservations, remaining allowance and the next settled charge
expiry. This is a rolling 24-hour window, not a midnight reset; unresolved holds
do not expire automatically. Global capacity and enrollment still apply.

The default evaluator is `https://3.21.93.126`; set `CATALYST_EVALUATOR_URL` to
use another trusted deployment. Public policy commands require no login.
