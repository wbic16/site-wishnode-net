#!/usr/bin/env bash
# deploy.sh — ship the site stack from this clone (on aletheia-core) to
# the wishnode.net host and run box-setup there. The host's GitHub deploy
# key is broken, so files move by scp, as with the other sites on the box.
set -euo pipefail
cd "$(dirname "$0")/.."
HOST=wbic16@44.248.235.76

ssh "$HOST" 'rm -rf ~/wishnode-stage && mkdir -p ~/wishnode-stage'
scp -q -r phexts backend scripts assets deploy "$HOST:wishnode-stage/"
# Wheels as an install fallback if the box cannot reach PyPI.
WHEELS=$(mktemp -d)
python3 -m pip download -q phext==0.3.2 -d "$WHEELS" 2>/dev/null && \
  scp -q -r "$WHEELS" "$HOST:wishnode-stage/wheels" || \
  echo "note: wheel staging skipped (box will try PyPI directly)"
rm -rf "$WHEELS"
ssh "$HOST" 'bash ~/wishnode-stage/scripts/box-setup.sh ~/wishnode-stage'
echo "deploy complete"
