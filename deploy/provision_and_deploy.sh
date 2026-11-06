#!/usr/bin/env bash
# Create a new Vultr VM and deploy this app to it. Idempotent for the label.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

python3 deploy/vultr_provision.py "$@"
IP="$(python3 -c "import json;print(json.load(open('.deploy-server.json'))['ip'])")"
DOMAIN="$(python3 -c "import json;print(json.load(open('.deploy-server.json'))['domain'])")"

echo "Waiting for SSH on $IP…"
for _ in $(seq 1 60); do
  if ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=5 \
       -o BatchMode=yes "root@$IP" true 2>/dev/null; then
    break
  fi
  sleep 5
done

CONSULT_HOST="root@$IP" CONSULT_DOMAIN="$DOMAIN" ./deploy/deploy.sh
echo
echo "Deployed: https://$DOMAIN/"
