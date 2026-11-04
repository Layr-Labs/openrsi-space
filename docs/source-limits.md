# Harness source limits

The batched-review service accepts up to **8 MiB (8,388,608 bytes) of expanded
submitted source** by default. The ZIP archive also has a separate **8 MiB** upload
limit. Both must fit. These are source-package limits, not Docker-image limits or
the solver's model-context limit. Generated snapshot metadata is excluded from
the expanded-source count.

For platform-funded runs, the required local-run evidence is a **separate private
upload**, capped at **192 MiB and 1,000 model calls**. Do not include it in the
public harness ZIP. Its recorded local budget cap must cover the remote cap; actual spending may be lower;
see [funded submission requirements](platform-funded-inference.md).

Check the deployed service rather than assuming a client update changed it:

```sh
uv run openrsi-space remote limits
uv run openrsi-space remote limits ./my-harness
```

The first command reads `GET /public/submission-policy` from the configured
evaluator. The second also measures your local harness, without uploading source,
reading model credentials or starting an evaluation. An older service may not
provide this endpoint yet; that is not confirmation that batched review is live.
Normal submission preparation also checks the default source and archive limits
locally. Server admission enforces its advertised expanded-source limit before
creating a new job. Operator-configured limits may be stricter.

Include the entrypoint, research loop, actual prompts/configuration, Dockerfile,
dependency lockfiles and required license notices. Remove unused web UI assets,
examples, tests, generated files, caches and unrelated vendored modules. Ordinary
dependency installation through the controlled build network is supported. Pin
dependencies for reproducibility; pins do not exempt imported content from policy.

Do not compress, encode or move task-specific material into dependencies to avoid
review. Source must remain inspectable text. An upstream executable can be larger
than the submitted text wrapper, but opaque bundled binaries are not automatically
accepted as source. Local Dungeness testing checks mechanics; it does not establish
remote screening acceptance.

Fitting the size limit does not guarantee approval. Source must remain inspectable
and satisfy the submission rules; review can fail when required material cannot
be assessed within the service's limits. Review spending is separate from your
research-model budget, so increasing the run cap does not resolve a review-capacity
error. Keep the reported request or evaluation ID when contacting support.

An oversized new request returns `413`, code `source_package_too_large`, field
`source.expanded_bytes`, and numeric `current`/`limit` byte counts. A later review
capacity failure identifies the review phase in owner diagnostics. Keep the request
or evaluation ID; remove unused files or contact the operator if required framework
code still cannot fit. Do not repeatedly submit unchanged source.

Source capture uses directory-relative, no-follow file descriptors. Symlinks,
special files and detected concurrent edits are rejected before packaging.
Keep the source directory stable while submitting; retry after stopping writers
if the CLI reports a changed path. Once captured, packaging and uploading use
those same immutable bytes. This is not a filesystem-wide transactional snapshot.
Secure capture requires POSIX no-follow descriptor support and real directory
components; resolve trusted symlinked workspace ancestors before submission.
