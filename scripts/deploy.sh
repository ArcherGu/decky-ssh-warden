#!/bin/bash
# Build, package and install the plugin on a Steam Deck over SSH.
# Usage: scripts/deploy.sh [user@host]   (default: deck@steamdeck)
# sudo on the Deck will ask for the deck user's password.
set -euo pipefail
cd "$(dirname "$0")/.."

HOST=${1:-deck@steamdeck}
NAME=decky-ssh-warden

pnpm build
bash scripts/package.sh
scp "out/$NAME.zip" "$HOST:/tmp/$NAME.zip"
ssh -t "$HOST" "sudo bash -c '
  set -e
  cd /home/deck/homebrew/plugins
  rm -rf $NAME
  unzip -q /tmp/$NAME.zip
  rm -f /tmp/$NAME.zip
  systemctl restart plugin_loader
'"
echo "Deployed to $HOST"
