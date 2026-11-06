#!/usr/bin/env bash
# Update the running app on the Vultr VM from this machine.
#
#   ./deploy/deploy.sh
#
# Requires an SSH alias (for example `vultr`) and rsync on the local machine.
# Override with CONSULT_HOST / CONSULT_DEST. Secrets stay on the server: .env is
# never copied.
set -euo pipefail

HOST="${CONSULT_HOST:-vultr}"
DEST="${CONSULT_DEST:-/opt/consult}"
SRC="$(cd "$(dirname "$0")/.." && pwd)"

echo "Syncing $SRC -> $HOST:$DEST"
rsync -az --delete \
    --exclude '.git' \
    --exclude '.venv' \
    --exclude 'out' \
    --exclude '.env' \
    --exclude '__pycache__' \
    --exclude '.pytest_cache' \
    "$SRC/" "$HOST:$DEST/"

ssh "$HOST" "chmod -R a+rX '$DEST' && '$DEST/.venv/bin/pip' install -q -r '$DEST/requirements.txt' && systemctl restart consult && sleep 2 && systemctl is-active consult"

echo "Health:"
ssh "$HOST" "curl -fsS http://127.0.0.1:8000/healthz" || true
echo
