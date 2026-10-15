# Preparing a public Catalyst release

The public distribution contains solver tools, source examples, the challenge
contract and workflow, and user documentation. The verification API, worker,
anti-cheat implementation, artifact storage and operational scripts belong only
in the private `catalyst-verifier` repository.

## History and release contents

Deleting or moving files does not remove them from previous Git commits,
submission branches or pull-request references. **Do not make the existing
repository public merely because this working tree no longer contains them.**
Use a reviewed snapshot with fresh history, or arrange a separately approved
history cleanup covering every reachable reference. Keep the existing repository
and private backups restricted until that is complete.

Export only an explicit reviewed inventory. Exclude `.git`, `.catalyst`, `.venv`,
credentials, run artifacts, environment files, generated metadata and old release
archives. Earlier archives prepared before the service split are superseded and
must not be published. The repository owner must approve a license; public
visibility alone does not grant one. Preserve third-party notices in examples.

Run public tests from the exported tree, inspect the built wheel and source
archive, and scan for private modules, source-review configuration and credentials.
Run the private cross-repository tests against that same public release.

Create a source-only export with an explicit path allowlist:

```sh
python3 scripts/export-public.py --output .catalyst/public-release
```

The command rejects unexpected files and existing destinations. Its
`PUBLIC_SOURCE.json` records each exported file's SHA-256. Review that inventory;
the export is not a GitHub publication and does not clean the original history.

Build release packages from that fresh export:

```sh
uv build --directory .catalyst/public-release
```

Do not reuse a pre-separation `build/` directory or old `*.egg-info` metadata:
setuptools can retain removed modules in its build cache and include them in a
wheel even when they no longer exist in `src/`. Inspect archive contents after
building; a successful build alone does not verify the public/private boundary.

## GitHub and Yukon identities

A new GitHub repository has a different numeric repository ID. Coordinate the
benchmark source and service's OIDC authorization before changing repositories,
then validate baseline and solver receipt retrieval. Preserve existing evidence,
benchmark IDs and evaluation IDs; do not silently replace them.

The source extraction alone does not deploy a service, alter GitHub visibility,
rewrite history, or change the registered Yukon benchmark.
