# syntax=docker/dockerfile:1
#
# DRAFT verifier image for ecdsa-fail. The candidate (src/point_add.rs) is
# untrusted; it is compiled and run here inside the clean no-network verifier.
# The trusted harness (evaluator/) supplies everything else and does the
# counting/validation. Rust deps are pre-fetched at build time so the runtime
# build is offline.
#
# NOTE: `rust:1.93.0-*` must exist for the pinned channel; if not, swap to a
# rustup base and `rustup toolchain install 1.93.0`. Resource limits and build
# timings still need a real run to size (a 200M-Toffoli sim over 64 shots is
# heavy).
FROM rust:1.93.0-bookworm

# python3 runs grade.py; `candidate` is the unprivileged user that compiles and
# runs the untrusted circuit code.
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --no-create-home --shell /usr/sbin/nologin --uid 10001 candidate

ENV CARGO_HOME=/opt/cargo

# The trusted harness = the crate minus src/point_add.rs (the candidate).
COPY evaluator/ /opt/evaluator/
COPY grade.py /tests/grade.py
COPY test.sh /tests/test.sh
# serve.py: same image, run as the agent-facing eval sidecar (docker-compose
# overrides CMD to run it). The one-shot verifier ignores it.
COPY serve.py /tests/serve.py

# Pre-fetch crate dependencies (network is available at build; runtime is not).
# `cargo fetch` only downloads deps and does not require the missing point_add.rs.
RUN cd /opt/evaluator \
    && cargo fetch \
    && mkdir -p /workspace /logs/verifier \
    && chown -R root:root /opt/evaluator /tests \
    && chmod -R go-rwx /opt/evaluator \
    && chmod 0555 /tests/test.sh /tests/grade.py /tests/serve.py \
    && chmod -R a+rX /opt/cargo

ENV CANDIDATE_PATH=/workspace/repo/src/point_add.rs \
    EVALUATOR_ROOT=/opt/evaluator \
    REWARD_PATH=/logs/verifier/reward.json \
    SCORE_PATH=/logs/verifier/score.json

CMD ["/tests/test.sh"]
