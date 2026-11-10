# Client and runtime compatibility

Before a new run, use `openrsi-space problem current` to discover the evaluator's
active release and exact problem digest. If it reports a mismatch, explain it
and ask before updating the client. Use the discovered `--problem-release` for
both local and remote runs. A release tag alone is not enough to establish an exact match.

Existing runs, local evidence and receipts retain their original identities.
Do not edit them to match a newer problem or retry an old operation with a new
request ID. A client update does not change a running evaluation.

## Current submission client

Yukon pins its receipt-checking revision. That checkout can contain an older
submission client. Follow the [separate-client setup](solver-guide.md#install-the-current-submission-cli)
and invoke `openrsi-space` directly from the benchmark directory. Keep Yukon's
receipt checker pinned; do not reset the benchmark checkout to upgrade the client.

## Check for updates

Before a new run or when diagnosing a possible platform issue, compare the
installed client's Git revision with the matching environment's published main:

```sh
git ls-remote https://github.com/Layr-Labs/openrsi-space.git refs/heads/main
```

Read the installed revision from the installation record or the installed package's
`direct_url.json` field `vcs_info.commit_id`. For a source installation, use that
checkout's HEAD and note local modifications. `--version` alone does not identify
the revision. Read only the revision, not full installation metadata, which may
contain private URLs. If the revision or network check is unavailable, report
“update status unknown”; this does not require a Yukon key or invalidate a run.

Different commits do not by themselves prove an update is needed: confirm the
repository/environment and inspect relevant changes. Tell the human what the
update fixes and ask before replacing an existing installation, unless they
already authorized that update. After approval, run:

```sh
uv tool install --force --refresh "git+https://github.com/Layr-Labs/openrsi-space.git@main"
```

Record the installed revision and rerun preparation checks. Use the client's
tested Dungeness pin, not Dungeness main independently. Never replace the client
or runtime during an active run. Preserve saved evidence, requests and receipts.
An update does not authorize a paid retry or resume an ended research process.

## Local runtime compatibility

The CLI manages a tested Dungeness revision for all supported problems. The
single authoritative pin is `REVISION` in
[`managed_runtime.py`](../src/openrsi_space/integrations/dungeness/managed_runtime.py).
`openrsi-space local run` downloads that exact revision on first use into
`$XDG_CACHE_HOME/openrsi-space/runtimes/dungeness/COMMIT` (default:
`~/.cache/openrsi-space/runtimes/dungeness/COMMIT`). Subsequent runs reuse it,
including offline when the other required dependencies and images are available.
Runtime download/preparation makes no model calls.

Updating the CLI may select a newer tested runtime. It does not modify a running
or retained evaluation. Each new run records its exact runtime commit and keeps
an independent copy, so removing a cached revision does not damage existing runs.
Downloads are locked and installed atomically; failed downloads do not fall back
to an older runtime. Modified or incomplete caches produce an actionable error.
The existing runtime capability checks still apply.

For development, `--dungeness /absolute/path/to/checkout` explicitly overrides
the managed pin. Keep that checkout clean; the CLI does not update it for you.
Use `dungeness capabilities` and `dungeness providers` there to inspect support.
Do not edit capability declarations to bypass a failed compatibility check.
If the service reports a release mismatch, retain your evidence and contact
support before repeating paid work. Local runtime selection does not change the
runtime deployed on the hosted evaluator.

Release maintainers: update the pin only after testing the new runtime against
all supported problems and coordinating the hosted runtime release. CLI-only
changes can keep the existing pin. Test first download, cache reuse, explicit
overrides and preparation from the installed package before publishing a release.

For a bug report, include `openrsi-space --version`, the Dungeness Git revision,
and whether either checkout has local changes. For a source installation, also
include the OpenRSI Git revision; a package version alone may not identify a
particular development commit. See the [changelog](../CHANGELOG.md).

## Conversation-history compatibility

Dungeness revision `df708b29249da5e5c80e7dfb32178452d6cd59a6` adds support for
OpenRouter reasoning format/signature metadata and safe continuation diagnostics.
Use that revision or a newer compatible runtime for local runs that replay this
history. The managed default follows the CLI pin. An explicitly supplied `--dungeness`
checkout must still be updated separately.

Dungeness revision `dbe7ee52974d25ddb109b5759491086d22bcf8f9` adds safe structural
paths and fixed rejection rules, without changing accepted history. The CLI
preserves these fields in local and authenticated owner diagnostics. No UI
update is needed.

If diagnostics report `conversation_history_rejected`, retain the request ID,
structural path and validation rule and contact support. Operators can collect
related incidents and release compatibility fixes together. Do not strip reasoning, signatures or
encrypted history. The rejection says whether the request reached the provider;
earlier usage and candidate results remain recorded. A runtime update does not
resume an already failed research process or automatically start paid work.
