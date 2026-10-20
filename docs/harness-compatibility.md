# Pair the harness with its model access

Choosing `--provider` and `--model` selects routing, credentials and pricing.
It does not rewrite the API requests emitted by your agent framework. Match the
framework and version, its adapter, the provider's supported API, the exact model,
and the credential method before submission. A working login or price quote
does not establish that the harness can run.

Use this process when creating or reusing a harness:

1. Inspect every model client the framework launches, including title generation,
   summarization, compaction and helper agents. Determine whether each uses
   Responses, Chat Completions, or another API. Check the selected provider in
   Catalyst's trusted [provider profiles](../src/catalyst/providers.json) and its
   [access instructions](live-models.md). An unlisted provider needs operator
   support; the harness cannot supply arbitrary upstream URLs.
2. Route all model requests through the endpoints and model identities assigned
   in `CATALYST_TASK`. Package any necessary API adapter in the harness. Test tool
   definitions, named tool choice, tool results, streaming responses and usage
   reporting. Translate both requests and responses when the protocols differ.
   Disable unsupported provider-hosted tools and unmetered fallback clients.
3. Select the matching private credential option. For example,
   `grok-subscription/grok-4.7` uses `--grok-auth-file`; direct `xai` uses an API
   key. Credentials stay outside the source and reach only the trusted gateway.
   Subscription login does not imply an API-key account or permission to fall
   back to one.
4. Run the packaging/entrypoint smoke checks and exercise the adapter against a
   strict mock of the selected API, including auxiliary requests and a complete
   tool-call round trip. A mock should reject malformed fields rather than return
   success for any JSON. `catalyst harness smoke` alone does not test live provider
   compatibility. A full local Dungeness run is optional.
5. Report the tested framework version, provider/model/access method, supported
   API operations and any untested boundary in the readiness report. A live
   compatibility run consumes model allowance and needs the user's authorization
   for remote credential use and a finite budget; reuse authorization already
   given. Do not claim a successful research run from a build or mock test alone.

## Example: Grok's session-title helper

The Grok CLI's main client uses Chat Completions, while its title helper uses
Responses. The subscription integration exposes Chat Completions. A Responses
function definition has `name`, `description` and `parameters` next to `type`;
Chat Completions requires those fields inside `function`. A named `tool_choice`
also needs `function: {"name": "..."}`. The
[stock Grok example](../examples/stock-grok) translates both, even though both
clients select the same model. A correct main request does not validate helper
requests.

For rejected requests, Dungeness retains the provider error and accounting basis.
Only recognized rejections before generation can settle at zero tokens. Missing
usage from successful responses, interrupted streams and ambiguous provider
errors still block further inference. Do not work around these checks or invent
usage in the harness adapter.
