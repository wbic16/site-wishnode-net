#!/usr/bin/env bash
# install_exo_apps.sh — build the five Exocortexia demo apps and install
# them on the wishnode.net host as systemd user units (task 27.6.8).
#
# Run ON aletheia-core (it holds the GitHub SSH key and the Exocortexia
# clone). Idempotent: safe to re-run after a source update.
#
#   EXO_SRC  path to the wbic16/Exocortexia clone (default ~/exo-verify)
#   HOST     ssh target of the site host (default wbic16@44.248.235.76)
#
# What it does:
#   1. cargo build --release in $EXO_SRC (binaries stay out of this repo)
#   2. scp the five release binaries to ~/exocortexia/bin/ on the host
#      and print local + remote SHA-256 for comparison
#   3. create ~/exocortexia/exo.env on the host if missing (EXO_AUDIT_KEY
#      generated ON THE HOST, mode 0600, never printed, never in a repo)
#   4. install deploy/systemd/exo-*.service, daemon-reload, enable+restart
#   5. smoke-check each app on its localhost port
set -euo pipefail
cd "$(dirname "$0")/.."

EXO_SRC="${EXO_SRC:-$HOME/exo-verify}"
HOST="${HOST:-wbic16@44.248.235.76}"
APPS="records-desk minutes-publisher contract-ledger data-catalog forms-router"

echo "== build (in $EXO_SRC) =="
cd "$EXO_SRC"
git rev-parse --short HEAD
cargo build --release
cd - >/dev/null

echo "== ship binaries =="
ssh "$HOST" 'mkdir -p ~/exocortexia/bin ~/exocortexia/state'
for app in $APPS; do
  ssh "$HOST" "mkdir -p ~/exocortexia/state/$app"
  scp -q "$EXO_SRC/target/release/$app" "$HOST:exocortexia/bin/$app"
  ssh "$HOST" "chmod +x ~/exocortexia/bin/$app"
  echo "-- $app"
  sha256sum "$EXO_SRC/target/release/$app" | awk '{print "  local  " $1}'
  ssh "$HOST" "sha256sum ~/exocortexia/bin/$app" | awk '{print "  remote " $1}'
done

echo "== host env (first run only; key generated on the host) =="
ssh "$HOST" 'if [ ! -f ~/exocortexia/exo.env ]; then
  umask 077; printf "EXO_AUDIT_KEY=%s\n" "$(openssl rand -hex 32)" > ~/exocortexia/exo.env
  echo "created ~/exocortexia/exo.env (0600)"
else echo "~/exocortexia/exo.env already present — left alone"; fi'

echo "== units =="
for app in $APPS; do
  scp -q "deploy/systemd/exo-$app.service" "$HOST:.config/systemd/user/exo-$app.service"
done
ssh "$HOST" 'systemctl --user daemon-reload
for app in records-desk minutes-publisher contract-ledger data-catalog forms-router; do
  systemctl --user enable exo-$app.service >/dev/null
  systemctl --user restart exo-$app.service
done
systemctl --user is-active exo-records-desk exo-minutes-publisher exo-contract-ledger exo-data-catalog exo-forms-router'

echo "== smoke check (host localhost) =="
ssh "$HOST" 'for p in 8801 8802 8803 8804 8805; do
  printf "port %s -> HTTP " $p
  curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:$p/
done'
echo "install_exo_apps complete"
