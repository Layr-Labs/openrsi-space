FROM node:22-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 git ripgrep ca-certificates curl poppler-utils \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g @openai/codex@0.153.3
COPY agent.py population.py snapshots.py gateway_adapter.py workflow.md strategy.schema.json /opt/harness/
WORKDIR /workspace/repo
