# Client and runtime compatibility

Before a new run, use `openrsi-space problem current` to discover the evaluator's
active release and exact problem digest. Update the client if it reports a
mismatch, and use the discovered `--problem-release` for both local and remote
runs. A release tag alone is not enough to establish an exact match.

Existing runs, local evidence and receipts retain their original identities.
Do not edit them to match a newer problem or retry an old operation with a new
request ID. A client update does not change a running evaluation.

## Current submission client

Yukon pins its receipt-checking revision. That checkout can contain an older
submission client. Follow the [separate-client setup](solver-guide.md#use-the-current-submission-client-with-a-pinned-yukon-board)
and invoke `openrsi-space` directly from the benchmark directory. Keep Yukon's
receipt checker pinned; do not reset the benchmark checkout to upgrade the client.

## Local runtime compatibility

Local testing requires a compatible public Dungeness checkout. It must advertise
the capabilities required by the client, including provider discovery. Check:

```sh
/path/to/dungeness/dungeness capabilities
/path/to/dungeness/dungeness providers
```

If preparation reports missing capabilities, use a fresh checkout at an unused
path so existing runs and working changes remain intact:

```sh
git clone https://github.com/Layr-Labs/dungeness.git /absolute/path/to/dungeness-compatible
/absolute/path/to/dungeness-compatible/dungeness capabilities
/absolute/path/to/dungeness-compatible/dungeness providers
```

Retry with `--dungeness /absolute/path/to/dungeness-compatible`. Do not edit a
runtime's capability declaration to bypass a failed compatibility check. A local
checkout does not establish which revision the hosted evaluator uses. If the
service reports a release mismatch, retain your local evidence and report it to
support before repeating paid work.

For a bug report, include `openrsi-space --version`, the Dungeness Git revision,
and whether either checkout has local changes. For a source installation, also
include the OpenRSI Git revision; a package version alone may not identify a
particular development commit. See the [changelog](../CHANGELOG.md).
