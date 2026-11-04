# Public source boundary

OpenRSI contains the solver CLI, challenge statement and contract, receipt-only
Yukon workflow, and public tests and documentation. The verification API, workers,
anti-cheat implementation, artifact storage and deployment tooling belong in the
private `openrsi-space-verifier` repository. The challenge UI belongs in Yukon.

Removing files from the current tree does not remove them from Git history or
old pull-request references. Before changing repository visibility, maintainers
must review the reachable history and release archives for private implementation
and credentials. Any history rewrite or repository replacement is a separate
operation that must preserve the GitHub/Yukon identity and authentication bindings.

Publish only reviewed source. Exclude `.openrsi`, `.venv`, credentials, evaluation
artifacts and generated build metadata. Build packages from a clean source tree;
stale build directories can accidentally reintroduce removed modules. Inspect
the final wheel and source archive as well as running the client and private
cross-repository tests. Repository visibility alone does not grant a source license.

Deleting bundled examples or removing the tracked submission directory does not
change retained evaluation IDs or grant permission to publish anyone's artifacts.

The registered Pareto benchmark keeps `submission/verification.json` as its
editable upload path. Solvers create that directory only to copy their receipt;
it is not a bundled harness. The root `verification.json` supplies the retained
baseline when no solver receipt is present. Keep the registered upload path
stable so existing benchmark IDs, submissions and pinned workflows remain usable.
