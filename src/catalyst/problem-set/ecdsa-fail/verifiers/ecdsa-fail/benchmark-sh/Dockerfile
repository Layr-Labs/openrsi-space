# syntax=docker/dockerfile:1
#
# Verifier image for ecdsa-fail checkpoints using benchmark-sh. The candidate (the
# src/point_add/ module) is untrusted; it is compiled and run here inside the
# clean no-network verifier by the UPSTREAM repo's own benchmark.sh (untrusted
# build_circuit -> trusted eval_circuit -> score.json). The trusted harness
# (evaluator/) supplies everything else. Rust deps are pre-fetched at build time
# so the runtime build is offline.
#
# NOT YET COMPILE-TESTED: the pinned channel (1.93.0) matches the source history;
# and build timings still need a real run (a heavy multi-shot simulation).
FROM rust:1.93.0-bookworm

# python3 runs grade.py; util-linux provides `setsid` (benchmark.sh isolates the
# untrusted build_circuit in its own process group); `candidate` is the
# unprivileged user that compiles and runs the untrusted circuit code.
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 util-linux \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --no-create-home --shell /usr/sbin/nologin --uid 10001 candidate

ENV CARGO_HOME=/opt/cargo

# The trusted harness = the upstream grading files (benchmark.sh + bins + crate
# harness), minus src/point_add/ (the candidate, transferred separately).
COPY evaluator/ /opt/evaluator/
COPY grade.py /tests/grade.py
COPY test.sh /tests/test.sh
# serve.py: same image, run as the agent-facing eval sidecar (compose overrides
# CMD to run it). The one-shot verifier ignores it.
COPY serve.py /tests/serve.py

# Pre-fetch crate dependencies (network is available at build; runtime is not).
# `cargo fetch` only reads Cargo.toml/Cargo.lock and does not require the missing
# src/point_add/ module.
RUN cd /opt/evaluator \
    && cargo fetch --locked \
    && mkdir -p /workspace /logs/verifier \
    && chown -R root:root /opt/evaluator /tests \
    && chmod -R go-rwx /opt/evaluator \
    && chmod 0555 /tests/test.sh /tests/grade.py /tests/serve.py \
    && chmod -R a+rX /opt/cargo

ENV CANDIDATE_PATH=/workspace/repo/src/point_add \
    EVALUATOR_ROOT=/opt/evaluator \
    REWARD_PATH=/logs/verifier/reward.json \
    SCORE_PATH=/logs/verifier/score.json

CMD ["/tests/test.sh"]
