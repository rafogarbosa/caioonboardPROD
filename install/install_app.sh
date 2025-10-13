# cria venv
python3 -m venv /xcoutfy/venv

# instala dependências
source /xcoutfy/venv/bin/activate
pip install -U pip wheel
pip install -r requirements.txt || echo "⚠️ Nenhum requirements.txt encontrado, ignorando."

# cria .env com variáveis básicas
echo "⚙️ Creating environment file (.env)..."
ENV_FILE="/xcoutfy/.env"
DEVICE_NAME=$(hostname)
cat <<EOF > "$ENV_FILE"
# Google Sheets
GOOGLE_SHEETS_CREDENTIALS=/xcoutfy/credentials.json
SHEET_NAME=dbgravacoes
SHEET_REGISTERS=registros
SHEET_AGENDA=agenda

# Rclone
RCLONE_REMOTE=xcoutfyvideos
RCLONE_FOLDER=[XCOUTFY]Vídeos/2025_VideosCAMUSB

# Outros
DEVICE_NAME=$DEVICE_NAME
LOG_LEVEL=INFO
EOF
echo "✅ DEVICE_NAME definido automaticamente como $DEVICE_NAME"

# ==========================
# Ativa systemd services
# ==========================
echo "🧠 Installing systemd services..."
SYSTEMD_DIR="/xcoutfy/install/systemd"

if ls $SYSTEMD_DIR/xcoutfy-*.service >/dev/null 2>&1; then
  sudo cp $SYSTEMD_DIR/xcoutfy-*.service /etc/systemd/system/
  sudo systemctl daemon-reexec
  sudo systemctl daemon-reload
  sudo systemctl enable xcoutfy-agenda.service xcoutfy-upload.service
  sudo systemctl restart xcoutfy-agenda.service xcoutfy-upload.service
  echo "✅ Systemd services configurados e iniciados"
else
  echo "⚠️ Nenhum arquivo .service encontrado em $SYSTEMD_DIR"
fi

echo "✅ App installed."
