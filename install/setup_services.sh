#!/bin/bash
set -euo pipefail
echo "🧠 Installing systemd services..."

sudo cp /xcoutfy/install/systemd/xcoutfy-*.service /etc/systemd/system/
sudo cp /xcoutfy/install/systemd/xcoutfy-*.timer   /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable xcoutfy-agenda.service
sudo systemctl enable xcoutfy-upload.service
sudo systemctl enable xcoutfy-update.timer

sudo systemctl restart xcoutfy-agenda.service
sudo systemctl restart xcoutfy-upload.service
sudo systemctl start   xcoutfy-update.timer

echo "✅ Services enabled and running."
