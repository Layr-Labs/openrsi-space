#!/bin/sh
# Run on the existing VM with Catalyst stopped, after uploading the source and Dungeness bundle.
# Usage: sudo sh provision-remote.sh SOURCE_TARBALL DUNGENESS_BUNDLE OWNER_UUID RELEASE_ID
set -eu
archive=$1
bundle=$2
owner_id=$3
release_id=$4
case "$release_id" in *[!a-zA-Z0-9-]*|'') exit 2;; esac
if sudo -u catalyst screen -S catalyst -Q windows >/dev/null 2>&1; then
  echo "Stop the existing Catalyst screen session before installing a release." >&2
  exit 1
fi
release="/opt/catalyst/releases/$release_id"
test ! -e "$release"
install -d -o catalyst -g catalyst -m 755 "$release"
tar -xzf "$archive" -C "$release"
chown -R catalyst:catalyst "$release"
if [ ! -d /opt/catalyst/dungeness ]; then
  sudo -u catalyst git clone "$bundle" /opt/catalyst/dungeness
  sudo -u catalyst git -C /opt/catalyst/dungeness checkout --detach 506890937d75b659db714d3e02ea3d3cec3a1451
fi
test "$(sudo -u catalyst git -C /opt/catalyst/dungeness rev-parse HEAD)" = 506890937d75b659db714d3e02ea3d3cec3a1451
sudo -u catalyst /opt/catalyst/bootstrap/bin/uv sync --frozen --project "$release"
if [ ! -d /var/lib/catalyst/evaluator ]; then
  sudo -u catalyst "$release/.venv/bin/catalyst" remote-evaluator-init /var/lib/catalyst/evaluator \
    --dungeness /opt/catalyst/dungeness --owner-id "$owner_id"
fi
ln -s "$release" /opt/catalyst/current.new
mv -Tf /opt/catalyst/current.new /opt/catalyst/current
install -d -o catalyst -g catalyst -m 700 /var/lib/catalyst/evaluator/service
sudo -u catalyst screen -dmS catalyst -L -Logfile /var/lib/catalyst/evaluator/service/screen.log \
  /bin/sh /opt/catalyst/current/scripts/run-remote-service.sh
sudo -u catalyst screen -ls
