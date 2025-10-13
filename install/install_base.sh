#!/bin/bash
set -euo pipefail
echo "🔧 Applying Xcoutfy base setup..."

# Atualização leve
sudo apt update -y && sudo apt upgrade -y

# Instala apenas o essencial (sem pacotes de idioma)
sudo apt install -y --no-install-recommends python3-venv python3-pip ffmpeg v4l-utils rclone curl git net-tools language-pack-en
sudo update-locale LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8
export LANG=en_US.UTF-8

# Desativa IPv6
sudo bash -c 'cat > /etc/sysctl.d/99-disable-ipv6.conf <<EOT
net.ipv6.conf.all.disable_ipv6 = 1
net.ipv6.conf.default.disable_ipv6 = 1
net.ipv6.conf.lo.disable_ipv6 = 1
EOT'
sudo sysctl -p /etc/sysctl.d/99-disable-ipv6.conf

# DNS fixo global
sudo bash -c 'cat > /etc/resolv.conf <<EOT
nameserver 8.8.8.8
nameserver 1.1.1.1
EOT'
sudo chattr +i /etc/resolv.conf || true

# Estrutura de pastas padrão
sudo mkdir -p /xcoutfy/{logs,schedules,recorded_videos,uploaded_videos,broadcastdone,keys}
sudo chown -R orangepi:orangepi /xcoutfy
sudo chmod -R 775 /xcoutfy

echo "✅ Base setup applied (locales skipped)."
