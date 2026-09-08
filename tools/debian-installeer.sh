#!/usr/bin/env bash
# Vitalytics installeren in een Debian CT (Proxmox, bijv. op een Beelink mini pc):
# systeemgebruiker + virtualenv + geharde systemd-service die bij het booten
# meekomt en bij een crash herstart.
# Als root draaien, vanuit de projectmap (of via tools/): bash tools/debian-installeer.sh
set -e

APPDIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APPDIR"
SVC_USER="vitalytics"
PORT="${VITALYTICS_PORT:-5055}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Draai dit script als root (bv. sudo bash tools/debian-installeer.sh)."
  exit 1
fi

echo "1/6 Python3 + venv installeren..."
apt-get update -q
apt-get install -y -q python3 python3-venv

echo "2/6 Tijdzone Europe/Amsterdam zodat 'vandaag' klopt..."
timedatectl set-timezone Europe/Amsterdam 2>/dev/null \
  || ln -sf /usr/share/zoneinfo/Europe/Amsterdam /etc/localtime

echo "3/6 Systeemgebruiker '$SVC_USER' aanmaken (service draait niet als root)..."
id -u "$SVC_USER" >/dev/null 2>&1 \
  || useradd --system --home-dir "$APPDIR" --shell /usr/sbin/nologin "$SVC_USER"

echo "4/6 Virtualenv + dependencies (flask, waitress, garminconnect)..."
[ -d venv ] || python3 -m venv venv
./venv/bin/pip install --upgrade pip -q
./venv/bin/pip install -r requirements.txt -q

echo "5/6 Systemd-service registreren..."
cat > /etc/systemd/system/vitalytics.service <<EOF
[Unit]
Description=Vitalytics - lokale gezondheidscoach
After=network-online.target
Wants=network-online.target

[Service]
User=$SVC_USER
Group=$SVC_USER
WorkingDirectory=$APPDIR
Environment=VITALYTICS_HOST=0.0.0.0
Environment=VITALYTICS_PORT=$PORT
ExecStart=$APPDIR/venv/bin/python app.py
Restart=always
RestartSec=3
# lichte hardening: geen privilege-escalatie, eigen tmp, systeemmappen read-only
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=full

[Install]
WantedBy=multi-user.target
EOF

mkdir -p data/uploads
chown -R "$SVC_USER:$SVC_USER" "$APPDIR"

systemctl daemon-reload
systemctl enable vitalytics >/dev/null
systemctl restart vitalytics

echo "6/6 Controle of de app reageert..."
ok=0
for i in 1 2 3 4 5; do
  sleep 2
  if "$APPDIR/venv/bin/python" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:$PORT/login', timeout=3)" 2>/dev/null; then
    ok=1; break
  fi
done
if [ "$ok" -eq 1 ]; then
  echo "   De app draait."
else
  echo "Let op: de app reageerde nog niet binnen 10 s — bekijk: journalctl -u vitalytics -n 50"
fi

echo
echo "Klaar. IP-adressen van deze CT:"
hostname -I
echo "Open op een apparaat in je thuisnetwerk:  http://<ip>:$PORT"
echo "Logs: journalctl -u vitalytics -f   |   Herstart: systemctl restart vitalytics"
echo "Firewall: geen aan in een standaard CT; bij de Proxmox-firewall poort 5055/tcp toestaan."