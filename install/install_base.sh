#!/bin/bash
set -euo pipefail
echo "🔧 Applying Xcoutfy base setup (minimal, no locales)..."

# evita qualquer prompt interativo e pacote de idioma
export DEBIAN_FRONTEND=noninteractive
export LC_ALL=C
export LANGUAGE=C
export LANG=C

# atualização leve e silenciosa
sudo apt-get -o Dpkg::Options::="--force-confnew" update -y
sudo apt-get -o Dpkg::Options::="--force-confnew" upgrade -y

# instala só o essencial — nada de idioma
sudo apt-get install -y --no-install-recommends \
  python3-venv python3-pip ffmpeg v4l-utils rclone curl git net-tools

# DNS fixo global
sudo bash -c 'cat > /etc/resolv.conf <<EOT
nameserver 8.8.8.8
nameserver 1.1.1.1
EOT'
sudo chattr +i /etc/resolv.conf || true

# estrutura de pastas
sudo mkdir -p /xcoutfy/{logs,schedules,recorded_videos,uploaded_videos,broadcastdone,keys}
sudo chown -R orangepi:orangepi /xcoutfy
sudo chmod -R 775 /xcoutfy

echo "✅ Base setup applied (no locales, fast build)."
