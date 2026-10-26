# Changelog

## Unreleased

- Derive provider availability from the selected Dungeness runtime, without a
  Catalyst-owned profile registry. Requires `dungeness providers`.
- Retire direct xAI/Grok subscription profiles, credential helpers, CLI flags and
  the stock Grok example; retain historical receipt compatibility.

- Add `catalyst --version` for package-version reporting. Include the Git revision
  as well when reporting issues from a source checkout.
- Explain how to obtain a compatible Dungeness pin when required capabilities are
  missing, and how to turn an execution object into a complete harness manifest.
- Correct the library count to eight papers and clarify provider availability
  and hosted rollout status.
- Document the complete offline smoke task, workspace permissions and entrypoint
  environment; link to the live local test required by the submission workflow.
