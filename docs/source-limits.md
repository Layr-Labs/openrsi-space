# Harness source and build requirements

Use this reference to prepare a source package and reproducible build.
The [submission rules](cheat-filter.md) define permitted content;
[submission recovery guide](submission-recovery.md) explains failures and recovery.

## Source package limits

The hosted service accepts up to **8 MiB (8,388,608 bytes) of expanded
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
openrsi-space remote limits
openrsi-space remote limits ./my-harness
```

The first command reads `GET /public/submission-policy` from the configured
evaluator. The second also measures your local harness, without uploading source,
reading model credentials or starting an evaluation. An older service may not
provide this endpoint yet; check with the operator rather than assuming its limits.
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

Symlinks, special files and detected concurrent edits are rejected before packaging.
Keep the source directory stable while submitting; retry after stopping writers
if the CLI reports a changed path. Use a supported POSIX environment and resolve
trusted symlinked workspace ancestors before submission.

## Build requirements

Hosted builds support normal Dockerfiles and online dependency
installation inside OpenRSI's isolated builder. Use ordinary apt, pip/uv, npm,
Cargo and Git workflows on hosts permitted by the existing build network policy.
Multi-stage Dockerfiles and compiled dependencies are supported. No OpenRSI-specific
download manifest, offline packaging or per-binary approval is required.

Pin image digests and dependency versions/lockfiles for reproducible builds. A pin
identifies content; it does not establish that a dependency complies with challenge
rules. Submitted prompts, build instructions and dependencies must remain general-
purpose. Do not embed solutions, task-specific strategies or guidance selecting a
particular paper. Agents may discover/select resources from the assigned library
during a fresh evaluation.

Review can examine both submitted source and the built image before execution.
Approval is specific to the reviewed submission; it does not establish that all
third-party code is safe or that a candidate will pass independent verification.
Review has limited coverage, especially for compiled dependencies. Ordinary
package installation is supported, but imported material must still comply with
the same submission rules.

Use local Dungeness testing to check harness mechanics before submitting. Existing
build-network, resource and timeout limits still apply. Keep the evaluation ID when
reporting a review failure. Service rollout status is separate from this documented
contract; updating the client does not activate a server policy.

## Dependency downloads during builds

Before submitting, inspect the hosted builder's current policy without uploading
source or credentials:

```sh
openrsi-space remote build-policy
```

The result lists the enabled profiles and allowed hosts, with a version and digest.
`include_subdomains: false` means only that exact host is allowed. Hosted defaults
cover common container/OS/source repositories, Python, Node.js/npm/NodeSource and
Rust releases/crates. Operators may configure a narrower set; the live response is
authoritative. The same data is available at `GET /public/build-policy`.

Pin dependencies and retain signature/hash verification. If a needed host is absent,
use a supported source or ask the operator to review adding it. A successful local
build does not prove that the hosted network policy permits every dependency.
Research containers still have no general internet access.

A failed remote build may report `BUILD_DEPENDENCY_HOST_BLOCKED`,
`BUILD_DEPENDENCY_ADDRESS_BLOCKED`, `BUILD_DEPENDENCY_PORT_BLOCKED`,
`BUILD_DEPENDENCY_DNS_FAILED` or `BUILD_DEPENDENCY_CONNECT_FAILED`, along with the
hostname and evaluation ID. Share these diagnostics with the operator. They are
observations from the proxy, not a definitive explanation of every build failure.
No research model calls begin during a failed build.
