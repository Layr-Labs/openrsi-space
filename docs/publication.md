# Public source boundary

Catalyst contains the solver CLI, challenge statement and contract, receipt-only
Yukon workflow, and public tests and documentation. The verification API, workers,
anti-cheat implementation, artifact storage and deployment tooling belong in the
private `catalyst-verifier` repository. The challenge UI belongs in Yukon.

Removing files from the current tree does not remove them from Git history or
old pull-request references. Before changing repository visibility, maintainers
must review the reachable history and release archives for private implementation
and credentials. Any history rewrite or repository replacement is a separate
operation that must preserve the GitHub/Yukon identity and authentication bindings.

Publish only reviewed source. Exclude `.catalyst`, `.venv`, credentials, evaluation
artifacts and generated build metadata. Build packages from a clean source tree;
stale build directories can accidentally reintroduce removed modules. Inspect
the final wheel and source archive as well as running the client and private
cross-repository tests. Repository visibility alone does not grant a source license.

Deleting local examples or moving the receipt to `verification.json` does not
change retained evaluation IDs or grant permission to publish anyone's artifacts.
