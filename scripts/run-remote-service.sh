#!/bin/sh
set -eu
# Image runtime files must be readable by non-root container users. The state
# root is private (0700); credential and trace files have explicit permissions.
umask 022
export PATH="/opt/catalyst/current/.venv/bin:/opt/catalyst/bootstrap/bin:/usr/local/bin:/usr/bin:/bin"
cd /opt/catalyst/current
exec .venv/bin/catalyst --state /var/lib/catalyst/evaluator/service evaluator-serve \
  --service-auth --auth-file /var/lib/catalyst/evaluator/auth.json \
  --problem-set /var/lib/catalyst/evaluator/problem-set.json --port 8778
