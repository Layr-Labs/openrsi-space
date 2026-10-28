# Harness source limits

The batched-review service accepts up to **8 MiB (8,388,608 bytes) of expanded
submitted source** by default. The ZIP archive also has a separate **8 MiB** upload
limit. Both must fit. These are source-package limits, not Docker-image limits or
the solver's model-context limit. Generated snapshot metadata is excluded from
the expanded-source count.

Check the deployed service rather than assuming a client update changed it:

```sh
uv run catalyst remote limits
uv run catalyst remote limits ./my-harness
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

Larger source is reviewed in bounded batches and a final cross-file review. All
source segments must receive a conclusive review before approval. Image review
remains explicitly partial for imported dependencies. Fitting the size limit does
not guarantee approval or completion within the operator's review budget and time
limits. Review spending is separate from your research-model budget; increasing
your run's credit cap does not increase screening capacity.

An oversized new request returns `413`, code `source_package_too_large`, field
`source.expanded_bytes`, and numeric `current`/`limit` byte counts. A later review
capacity failure identifies the review phase in owner diagnostics. Keep the request
or evaluation ID; remove unused files or contact the operator if required framework
code still cannot fit. Do not repeatedly submit unchanged source.
