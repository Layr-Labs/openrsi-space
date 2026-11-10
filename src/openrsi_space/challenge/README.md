# Challenge preparation

Shared code for loading trusted challenge definitions and preparing assigned run
inputs. Challenge descriptions, manifests, paper catalogs, scaffolds and verifier
bundles live beside this package in [`../problem-set/`](../problem-set).

- `catalog.py`: release lookup, statements and pinned local problem workspaces.
- `assets.py`: trusted scaffold/verifier registry and installation.
- `papers.py`: pinned paper downloads, integrity checks and local caching.
- `resources.py`: format-neutral resource catalogs and endpoint metadata.
- `preparation.py`: assigned task documents, problem-service files and Dungeness records.
- `paths.py`: the installed problem-set location.

The solver CLI and private verifier share this package. Submitted harnesses cannot
choose host preparation code or replace the assigned problem. The container's
standalone problem-service entrypoint remains in `../runtime/problem_server.py`.

The former top-level modules remain as compatibility imports for existing verifier
releases. They alias these modules, keeping configuration and behavior identical.
New callers should import `openrsi_space.challenge.*`.
