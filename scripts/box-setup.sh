#!/usr/bin/env bash
# box-setup.sh — install/update the wishnode.net stack on the site host.
# Runs ON the host as wbic16. Idempotent. Secrets are generated on first
# run, on the host, into 0600 files; they are never overwritten and never
# come from the repository.
# Usage: bash box-setup.sh [stage-dir]   (default ~/wishnode-stage)
set -euo pipefail

STAGE="${1:-$HOME/wishnode-stage}"
APP="$HOME/wishnode"
DOCROOT="/sites/web/wishnode.net"
TS=$(date +%Y%m%d%H%M%S)

mkdir -p "$APP/app" "$APP/data/pages" "$APP/data/intake" "$APP/data/citizen" \
         "$HOME/.config/systemd/user" "$DOCROOT/nginx" /sites/backups

# --- application files ------------------------------------------------------
cp "$STAGE/backend/wishnode_backend.py" "$APP/app/"
cp "$STAGE/scripts/render_site.py" "$APP/app/"
mkdir -p "$APP/app/assets"
cp "$STAGE/assets/site.css" "$APP/app/assets/site.css"

# --- python venv with libphext ----------------------------------------------
if [ ! -x "$APP/venv/bin/python" ]; then
  python3 -m venv "$APP/venv"
fi
"$APP/venv/bin/pip" install -q "phext==0.3.2" 2>/dev/null || \
  "$APP/venv/bin/pip" install -q "$STAGE"/wheels/*.whl || {
  echo "pip install failed from PyPI and from staged wheels" >&2; exit 1; }

# --- secrets (first run only) ------------------------------------------------
if [ ! -f "$APP/backend.env" ]; then
  PAGES_KEY=$(openssl rand -hex 32)
  INTAKE_KEY=$(openssl rand -hex 32)
  cat > "$APP/sq-tenants.json" <<EOF
{"tenants": {
  "$PAGES_KEY":  {"name": "wishnode-pages",  "data_dir": "$APP/data/pages"},
  "$INTAKE_KEY": {"name": "wishnode-intake", "data_dir": "$APP/data/intake"}
}}
EOF
  chmod 600 "$APP/sq-tenants.json"
  cat > "$APP/backend.env" <<EOF
WISHNODE_PORT=8940
WISHNODE_BIND=127.0.0.1
SQ_URL=http://127.0.0.1:8931
SQ_PAGES_KEY=$PAGES_KEY
SQ_INTAKE_KEY=$INTAKE_KEY
WISHNODE_DATA_DIR=$APP/data
WISHNODE_CSS_PATH=$APP/app/assets/site.css
WISHNODE_ADMIN_TOKEN=$(openssl rand -hex 32)
WISHNODE_CITIZEN_SECRET=$(openssl rand -hex 32)
WISHNODE_SESSION_SECRET=$(openssl rand -hex 32)
WISHNODE_SSO_AUD=wishnode
EDIT_SSO_LOGIN_URL=https://edit.phext.io/api/auth/sso/wishnode
# Demo mode is the explicit fail-closed opt-in (audit A-F02 pattern):
# the backend refuses to start without either full SSO config or this
# flag. REMOVE this line when WISHNODE_SSO_SECRET is provisioned below.
WISHNODE_DEMO_MODE=1
# WISHNODE_SSO_SECRET — add the shared edit.phext.io secret here (and only
# here) once Will deploys the lattice side; SSO stays off until then.
EOF
  chmod 600 "$APP/backend.env"
  echo "generated $APP/backend.env + sq-tenants.json (0600)"
fi

# --- phexts ------------------------------------------------------------------
for f in "$STAGE"/phexts/*.phext; do
  base=$(basename "$f")
  case "$base" in
    intake.phext)           cp "$f" "$APP/data/intake/" ;;
    citizen-template.phext) : ;;  # template only, not hosted
    *)                      cp "$f" "$APP/data/pages/" ;;
  esac
done

# --- systemd user units --------------------------------------------------------
cp "$STAGE/deploy/systemd/wishnode-sq.service" "$HOME/.config/systemd/user/"
cp "$STAGE/deploy/systemd/wishnode-backend.service" "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable wishnode-sq.service wishnode-backend.service >/dev/null

# Restart SQ AFTER the phext files change (a hosted phext replaced under a
# running daemon wedges it), then the backend.
systemctl --user restart wishnode-sq.service
sleep 2
systemctl --user restart wishnode-backend.service
sleep 1

# --- nginx snippet (inert until the one-line include is added by root) --------
cp "$STAGE/deploy/nginx/wishnode-dynamic.conf" "$DOCROOT/nginx/wishnode-dynamic.conf"

# --- back up the docroot files we are about to replace, then render -----------
BK="/sites/backups/wishnode.net-$TS"
mkdir -p "$BK"
for p in index.html ask.html status.html how-it-works.html exocortexia statutes assets; do
  [ -e "$DOCROOT/$p" ] && cp -a "$DOCROOT/$p" "$BK/"
done
echo "docroot backup: $BK"

set -a; . "$APP/backend.env"; set +a
OUT_DIR="$DOCROOT" CSS_PATH="$APP/app/assets/site.css" \
  python3 "$APP/app/render_site.py"

systemctl --user --no-pager status wishnode-sq.service wishnode-backend.service | head -20
echo "box-setup complete"
