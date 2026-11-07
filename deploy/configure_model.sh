#!/usr/bin/env bash
# Change the live VM's inference provider/key/model without rebuilding.
#   ./deploy/configure_model.sh
#   ./deploy/configure_model.sh --provider claude --model claude-sonnet-4-5
# The remote prompt reads the key with hidden input.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATE="$ROOT/.deploy-server.json"
HOST="${CONSULT_HOST:-}"
if [ -z "$HOST" ] && [ -f "$STATE" ]; then
  IP="$(python3 -c "import json;print(json.load(open('$STATE'))['ip'])")"
  HOST="root@$IP"
fi
if [ -z "$HOST" ]; then
  echo "Set CONSULT_HOST or keep .deploy-server.json." >&2
  exit 1
fi

ARGS=""
for arg in "$@"; do
  ARGS+=" $(printf '%q' "$arg")"
done

ssh -t -o StrictHostKeyChecking=accept-new -o ConnectTimeout=12 "$HOST" \
  "cd /opt/consult-homeopathic && \
   /opt/consult-homeopathic/.venv/bin/python scripts/configure_model.py \
     --env-file /opt/consult-homeopathic/.env$ARGS && \
   systemctl restart consult-homeopathic && sleep 2 && \
   curl -fsS http://127.0.0.1:8000/healthz"
