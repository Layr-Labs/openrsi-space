FROM node:22-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 git ripgrep ca-certificates poppler-utils \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g @openai/codex@0.153.3
COPY agent.py instructions.md /opt/harness/
COPY references/ /opt/harness/references/
RUN python3 /opt/harness/agent.py --check-references
WORKDIR /workspace/repo
