#!/bin/bash
set -euo pipefail
echo "🔄 Updating Xcoutfy from GitHub..."

export DEBIAN_FRONTEND=noninteractive
export LC_ALL=C
export LANGUAGE=C
export LANG=C

cd /xcoutfy
sudo systemctl stop xcoutfy-agenda.service xcoutfy-upload.service || true
git fetch --all
git reset --hard origin/main
sudo systemctl daemon-reexec
sudo systemctl daemon-reload
sudo systemctl restart xcoutfy-agenda.service xcoutfy-upload.service
echo "✅ Update completed successfully."
