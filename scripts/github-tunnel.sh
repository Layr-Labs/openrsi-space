#!/usr/bin/env bash
# Optional private transport for the receipt-only GitHub judge.
set -euo pipefail
umask 077

if [[ -n "${CATALYST_EVALUATOR_URL:-}" ]]; then
  [[ "$CATALYST_EVALUATOR_URL" == https://* ]] || {
    echo "Configure an HTTPS endpoint, or leave it empty to use the private SSH tunnel." >&2
    exit 1
  }
  exit 0
fi

: "${RUNNER_TEMP:?GitHub runner temporary directory is required}"
: "${GITHUB_ENV:?GitHub environment file is required}"
: "${CATALYST_SSH_KEY:?Configure a restricted repository tunnel key}"
: "${CATALYST_SSH_KNOWN_HOSTS:?Configure the verified VM host key}"
: "${CATALYST_SSH_HOST:?Configure the VM hostname or IP}"
: "${CATALYST_SSH_USER:?Configure the VM tunnel user}"
[[ "$CATALYST_SSH_HOST" =~ ^[a-zA-Z0-9.-]+$ ]] || exit 1
[[ "$CATALYST_SSH_USER" =~ ^[a-zA-Z_][a-zA-Z0-9_-]*$ ]] || exit 1

connection_dir="$RUNNER_TEMP/catalyst-tunnel"
mkdir -m 700 "$connection_dir"
printf '%s\n' "$CATALYST_SSH_KEY" > "$connection_dir/key"
printf '%s\n' "$CATALYST_SSH_KNOWN_HOSTS" > "$connection_dir/known_hosts"
ssh -fNT -M -S "$connection_dir/control" \
  -i "$connection_dir/key" \
  -o BatchMode=yes -o IdentitiesOnly=yes -o ExitOnForwardFailure=yes \
  -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$connection_dir/known_hosts" \
  -o ConnectTimeout=20 -o ServerAliveInterval=30 -o ServerAliveCountMax=2 \
  -L 127.0.0.1:18778:127.0.0.1:8778 \
  "$CATALYST_SSH_USER@$CATALYST_SSH_HOST"
printf '%s\n' 'CATALYST_EVALUATOR_URL=http://127.0.0.1:18778' >> "$GITHUB_ENV"
echo "Private verifier tunnel connected."
