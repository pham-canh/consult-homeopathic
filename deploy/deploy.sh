#!/usr/bin/env bash
# Sync this tree to the dedicated VM, install requirements, restart, and check.
#   ./deploy/deploy.sh
#   CONSULT_HOST=root@1.2.3.4 ./deploy/deploy.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATE="$ROOT/.deploy-server.json"
DEST="${CONSULT_DEST:-/opt/consult-homeopathic}"
ENV_DIR="/etc/consult-homeopathic"
SERVICE="consult-homeopathic"

IP=""
DOMAIN=""
if [ -f "$STATE" ]; then
  IP="$(python3 -c "import json;print(json.load(open('$STATE'))['ip'])")"
  DOMAIN="$(python3 -c "import json;print(json.load(open('$STATE'))['domain'])")"
fi
HOST="${CONSULT_HOST:-${IP:+root@$IP}}"
if [ -z "$HOST" ]; then
  echo "Set CONSULT_HOST or run deploy/vultr_provision.py first." >&2
  exit 1
fi
DOMAIN="${DOMAIN:-${CONSULT_DOMAIN:-}}"
SSH=(ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=12 "$HOST")

echo "Syncing $ROOT -> $HOST:$DEST"
"${SSH[@]}" "mkdir -p '$DEST' '$ENV_DIR'"
rsync -az --delete \
  --exclude '.git' --exclude '.venv' --exclude 'out' --exclude 'data' \
  --exclude '.env' --exclude '.deploy-server.json' \
  --exclude '__pycache__' --exclude '.pytest_cache' \
  "$ROOT/" "$HOST:$DEST/"

if ! "${SSH[@]}" "test -s '$ENV_DIR/consult.env'"; then
  if [ ! -f "$ROOT/.env" ]; then
    echo "No local .env to seed the server; create $ENV_DIR/consult.env manually." >&2
    exit 1
  fi
  if [ -z "$DOMAIN" ]; then
    echo "Set CONSULT_DOMAIN or keep .deploy-server.json to build the env file." >&2
    exit 1
  fi
  TMP="$(mktemp)"
  umask 077
  python3 - "$ROOT/.env" "$TMP" "$DOMAIN" <<'PY'
import sys
src, dst, domain = sys.argv[1], sys.argv[2], sys.argv[3]
drop = {"CONSULT_DATA_DIR", "CONSULT_PUBLIC_URL", "PORT", "CONSULT_DISABLE_SCHEDULER"}
lines = []
for raw in open(src, encoding="utf-8"):
    name = raw.split("=", 1)[0].strip()
    if raw.strip() and not raw.lstrip().startswith("#") and name in drop:
        continue
    lines.append(raw.rstrip("\n"))
lines += ["", "# Added by deploy/deploy.sh for this VM",
          "CONSULT_DATA_DIR=/var/lib/consult-homeopathic",
          f"CONSULT_PUBLIC_URL=https://{domain}", "PORT=8000"]
open(dst, "w", encoding="utf-8").write("\n".join(lines) + "\n")
PY
  scp -q "$TMP" "$HOST:$ENV_DIR/consult.env"
  rm -f "$TMP"
  "${SSH[@]}" "if id consult >/dev/null 2>&1; then chown root:consult '$ENV_DIR/consult.env'; fi; chmod 640 '$ENV_DIR/consult.env'"
fi

if ! "${SSH[@]}" "test -x '$DEST/.venv/bin/python'"; then
  if [ -z "$DOMAIN" ]; then
    echo "First run needs DOMAIN (use deploy/provision_and_deploy.sh)." >&2
    exit 1
  fi
  echo "Running first-time bootstrap on the server…"
  "${SSH[@]}" "DOMAIN='$DOMAIN' bash '$DEST/deploy/bootstrap.sh'"
else
  "${SSH[@]}" "'$DEST/.venv/bin/pip' install -q -r '$DEST/requirements.txt' && \
    install -m 644 '$DEST/deploy/consult-homeopathic.service' \
      '/etc/systemd/system/$SERVICE.service' && \
    systemctl daemon-reload && systemctl restart '$SERVICE' && \
    sleep 2 && systemctl is-active '$SERVICE'"
fi

echo "Health:"
"${SSH[@]}" "curl -fsS http://127.0.0.1:8000/healthz" || true
echo
if [ -n "$DOMAIN" ]; then
  echo "Public: https://$DOMAIN/"
  echo "Doctor: https://$DOMAIN/doctor"
fi
