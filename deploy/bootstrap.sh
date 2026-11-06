#!/usr/bin/env bash
# First-time server setup. Runs as root on a fresh Ubuntu 24.04 Vultr VM.
# The orchestrator rsyncs the code and writes the env file before calling this.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/consult-homeopathic}"
APP_USER="${APP_USER:-consult}"
DATA_DIR="${DATA_DIR:-/var/lib/consult-homeopathic}"
ENV_DIR="${ENV_DIR:-/etc/consult-homeopathic}"
SERVICE="${SERVICE:-consult-homeopathic}"
DOMAIN="${DOMAIN:?set DOMAIN to the public hostname}"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3-venv python3-pip rsync ca-certificates caddy ufw >/dev/null

# Host firewall. Vultr's firewall group can stay empty; this is the second layer.
ufw allow 22/tcp >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null

id -u "$APP_USER" >/dev/null 2>&1 || \
  useradd --system --user-group --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
mkdir -p "$APP_DIR" "$DATA_DIR" "$ENV_DIR" "$DATA_DIR/emails" "$DATA_DIR/reports"
chown -R "$APP_USER:$APP_USER" "$DATA_DIR"

if [ ! -x "$APP_DIR/.venv/bin/python" ]; then
  python3 -m venv "$APP_DIR/.venv"
fi
"$APP_DIR/.venv/bin/pip" install -q --upgrade pip wheel
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"
chown -R "$APP_USER:$APP_USER" "$APP_DIR/.venv"

install -m 644 "$APP_DIR/deploy/consult-homeopathic.service" \
  "/etc/systemd/system/$SERVICE.service"
chown root:"$APP_USER" "$ENV_DIR/consult.env"
chmod 640 "$ENV_DIR/consult.env"

cat > /etc/caddy/Caddyfile <<CADDY
$DOMAIN {
    encode gzip
    reverse_proxy 127.0.0.1:8000
}
CADDY

systemctl daemon-reload
systemctl enable --now "$SERVICE"
systemctl enable --now caddy
systemctl reload caddy 2>/dev/null || systemctl restart caddy

for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/healthz >/dev/null 2>&1; then
    echo "local health: ok"
    break
  fi
  sleep 2
done
curl -fsS "https://$DOMAIN/healthz" >/dev/null && echo "public health: ok" || \
  echo "public health: not ready yet (Caddy may still be issuing TLS)"
