FROM ghcr.io/astral-sh/uv:0.12.3 AS uv
FROM python:3.12-slim-bookworm
COPY --from=uv /uv /usr/local/bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
# Resolve code and Python dependencies at build time; execution has no internet.
RUN git init /opt/skydiscover \
    && git -C /opt/skydiscover remote add origin https://github.com/skydiscover-ai/skydiscover.git \
    && git -C /opt/skydiscover fetch --depth 1 origin 0d932b690670a7e544388ad362e9876c8bd256a0 \
    && git -C /opt/skydiscover checkout --detach FETCH_HEAD \
    && test "$(git -C /opt/skydiscover rev-parse HEAD)" = 0d932b690670a7e544388ad362e9876c8bd256a0 \
    && UV_PYTHON_DOWNLOADS=never uv sync --frozen --no-dev --project /opt/skydiscover
ENV PATH="/opt/skydiscover/.venv/bin:$PATH"
COPY skydiscover-compat.patch /opt/harness/skydiscover-compat.patch
# Empty system messages are rejected by some Chat Completions providers.
RUN git -C /opt/skydiscover apply --check /opt/harness/skydiscover-compat.patch \
    && git -C /opt/skydiscover apply /opt/harness/skydiscover-compat.patch
COPY agent.py evaluator.py /opt/harness/
WORKDIR /workspace/repo
