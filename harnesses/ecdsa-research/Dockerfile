FROM node:22-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 git ripgrep ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g @openai/codex@0.153.3
COPY agent.py /opt/harness/agent.py
WORKDIR /workspace/repo
