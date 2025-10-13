#!/bin/bash
set -euo pipefail
APP_DIR="/xcoutfy"
VENV="/xcoutfy/venv"
LOG="/xcoutfy/logs/update.log"

exec >> "$LOG" 2>&1
echo "---- $(date '+%Y-%m-%d %H:%M:%S') Updating app ----"

if [ ! -d "$APP_DIR/.git" ]; then
  echo "Repo not initialized in $APP_DIR. Skipping."
  exit 0
fi

cd "$APP_DIR"
OLD_REV=$(git rev-parse HEAD)
git fetch --all
git reset --hard origin/main
NEW_REV=$(git rev-parse HEAD)

if [ "$OLD_REV" != "$NEW_REV" ]; then
  echo "Changes detected: $OLD_REV -> $NEW_REV"
  source "$VENV/bin/activate" 2>/dev/null || true
  if [ -f requirements.txt ]; then
    pip install --upgrade pip
    pip install -r requirements.txt
  fi
  sudo systemctl restart xcoutfy-agenda.service || true
  sudo systemctl restart xcoutfy-upload.service || true
  echo "Services restarted after update."
else
  echo "No changes."
fi
