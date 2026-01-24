#!/bin/bash
# deploy.sh - Deploy Skylight to Raspberry Pi

set -e

PI_HOST="${PI_HOST:-skylight.local}"
PI_USER="${PI_USER:-pi}"
PI_PATH="${PI_PATH:-/home/pi/skylight}"

echo "Deploying Skylight to ${PI_USER}@${PI_HOST}..."

# Sync files
rsync -avz --delete \
  --exclude '.git' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude 'mockups' \
  --exclude '.DS_Store' \
  ./ "${PI_USER}@${PI_HOST}:${PI_PATH}/"

echo "Restarting services..."
ssh "${PI_USER}@${PI_HOST}" "sudo systemctl restart skylight-data skylight-http && sleep 2 && sudo systemctl restart skylight-display"

echo ""
echo "Deployed!"
echo "   View logs: ssh ${PI_USER}@${PI_HOST} 'journalctl -u skylight-data -f'"
