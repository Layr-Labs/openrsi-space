# Pair the harness with its model access

Choosing `--provider` and `--model` selects routing, credentials and pricing.
It does not rewrite the API requests emitted by your agent framework. Match the
framework and version, its adapter, the provider's supported API, the exact model,
and the credential method before submission. A working login or price quote
does not establish that the harness can run.

Use this process when creating or reusing a harness:

1. Inspect every model client the framework launches, including title generation,
   summarization, compaction and helper agents. Determine whether each uses
   Responses, Chat Completions, or another API. Check the
   [hosted provider permissions](live-models.md#implemented-providers-and-hosted-permission).
   The selected Dungeness runtime reports its trusted provider IDs through
   `dungeness providers`. OpenRSI uses that registry for both pricing quotes and
   submission admission. Solvers cannot supply upstream URLs or provider profiles.
   A provider absent from the runtime needs operator integration. For platform
   funding, also check `openrsi-space remote funding-policy`: select a funded API
   provider and your exact model, with service-validated pricing. The local trace
   must match the provider, model and reasoning settings of the remote request.
2. Route all model requests through the endpoints and model identities assigned
   in `CATALYST_TASK`. Package any necessary API adapter in the harness. Test tool
   definitions, named tool choice, tool results, streaming responses and usage
   reporting. Translate both requests and responses when the protocols differ.
   Disable unsupported provider-hosted tools and unmetered fallback clients.
3. For funded remote access, use `--platform-funded` and no personal model credential.
   Personal API-key submission is currently disabled and remote subscription
   handoffs have been removed. For local testing, use the private access option
   described in the local guide. A qualifying local evidence run must match the
   funded remote provider, model and reasoning settings.
4. Run the packaging/entrypoint smoke checks and exercise the adapter against a
   strict mock of the selected API, including auxiliary requests and a complete
   tool-call round trip. A mock should reject malformed fields rather than return
   success for any JSON. `openrsi-space harness smoke` alone does not test live provider
   compatibility. Complete a [local Dungeness run](local-evaluation.md) before
   remote submission; the CLI reuses a matching local record, with an explicit
   `--skip-local-check` override for user-funded runs. Funded admission requires
   a matching private local bundle and the full remote cap in settled local usage;
   the flag cannot bypass that gate without an operator exemption.
5. Report the tested framework version, provider/model/access method, supported
   API operations and any untested boundary in the readiness report. A live
   compatibility run consumes model allowance and needs the user's authorization
   for remote credential use and a finite budget; reuse authorization already
   given. Do not claim a successful research run from a build or mock test alone.

## Example: helper requests using a different API

Inspect auxiliary clients such as session-title generation as well as the main
research loop. A Responses function definition has `name`, `description` and
`parameters` next to `type`; Chat Completions requires those fields inside
`function`. A named `tool_choice` also needs `function: {"name": "..."}`. If the
framework and chosen endpoint differ, the harness must adapt both requests and
responses, including helper requests. A successful main request alone is not a
complete compatibility test.

For rejected requests, Dungeness retains the provider error and accounting basis.
Only recognized rejections before generation can settle at zero tokens. Missing
usage from successful responses, interrupted streams and ambiguous provider
errors still block further inference. Do not work around these checks or invent
usage in the harness adapter.

Harness packaging rejects common login files and credential directories (such as
`auth.json`, `.aws`, `.ssh`, `.codex`, and `token.txt`) before reading their
contents. Keep model credentials outside the source directory and pass them
through the CLI's credential options. This local filename check is an early
safeguard; the verifier separately scans source contents before review or publication.
