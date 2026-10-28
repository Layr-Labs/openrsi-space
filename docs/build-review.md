# Harness build review

Before submitting, check the [source-size limits](source-limits.md): by default,
both expanded submitted source and its ZIP must fit 8 MiB. Large text packages use
bounded batch reviews followed by a cross-file review; Docker image size is separate.

The revised two-stage review supports normal Dockerfiles and online dependency
installation inside Catalyst's isolated builder. Use ordinary apt, pip/uv, npm,
Cargo and Git workflows on hosts permitted by the existing build network policy.
Multi-stage Dockerfiles and compiled dependencies are supported. No Catalyst-specific
download manifest, offline packaging or per-binary approval is required.

Pin image digests and dependency versions/lockfiles for reproducible builds. A pin
identifies content; it does not establish that a dependency complies with challenge
rules. Submitted prompts, build instructions and dependencies must remain general-
purpose. Do not embed solutions, task-specific strategies or guidance selecting a
particular paper. Agents may discover/select resources from the assigned library
during a fresh evaluation.

Source review happens before building. A second review examines the returned image
before execution and model credential handoff. Its approval is tied to that exact
image. It inventories final-image layers, including files deleted by later layers,
and semantically reviews a bounded selection of text alongside the original source.

This is explicitly **partial coverage**: opaque binaries, omitted text, downloaded
bodies, discarded stages and files created/deleted within one build step are not
fully inspected. Their presence alone does not reject a normal package installation;
specific suspicious evidence can still reject the harness or make review inconclusive.
A pass is not proof of complete dependency inspection or independent research.

Use local Dungeness testing to check harness mechanics before submitting. Existing
build-network, resource and timeout limits still apply. Keep the evaluation ID when
reporting a review failure. Service rollout status is separate from this documented
contract; updating the client does not activate a server policy.
