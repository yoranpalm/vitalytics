#!/usr/bin/env bash
# Vitalytics bijwerken op de Debian-server/CT: nieuwe code is al overgezet
# (bijv. met tools/naar-server.ps1); dit verversert dependencies en herstart.
# Als root draaien: bash tools/debian-update.sh
set -e

APPDIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APPDIR"
SVC_USER="vitalytics"

if [ "$(id -u)" -ne 0 ]; then
  echo "Draai dit script als root (bv. sudo bash tools/debian-update.sh)."
  exit 1
fi

echo "1/3 Dependencies verversen (flask, waitress, garminconnect)..."
./venv/bin/pip install -r requirements.txt -q

echo "2/3 Rechten zetten..."
mkdir -p data/uploads
chown -R "$SVC_USER:$SVC_USER" "$APPDIR"

echo "3/3 Service herstarten..."
systemctl restart vitalytics
sleep 2
systemctl --no-pager status vitalytics | head -n 5 || true
echo "Logs: journalctl -u vitalytics -f"