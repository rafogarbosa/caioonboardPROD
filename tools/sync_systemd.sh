#!/bin/bash
echo "🔄 Atualizando código e systemd..."
cd /xcoutfy || exit

git fetch origin && git reset --hard origin/main

sudo cp /xcoutfy/systemd/xcoutfy-* /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl list-units --type=service | grep xcoutfy-

echo "✅ Sincronização concluída."
