FROM node:22-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 git ripgrep ca-certificates curl poppler-utils \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL https://x.ai/cli/install.sh | bash -s -- 1.0.62 \
    && install -m 0755 "$(readlink -f /root/.local/bin/grok || echo /root/.grok/bin/grok)" /usr/local/bin/grok \
    && grok --version
COPY agent.py gateway_adapter.py mint_auth.py /opt/harness/
WORKDIR /workspace/repo
