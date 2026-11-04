# Harness build review

Before submitting, check the [source-size limits](source-limits.md): by default,
both expanded submitted source and its ZIP must fit 8 MiB. Large text packages use
bounded batch reviews followed by a cross-file review; Docker image size is separate.

The revised two-stage review supports normal Dockerfiles and online dependency
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
