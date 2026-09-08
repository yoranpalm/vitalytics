# Stuurt de Vitalytics-projectmap via SSH naar een Debian-server/CT (Proxmox)
# en installeert/start de app daar met tools/debian-installeer.sh.
#
# Gebruik:   powershell -File tools\naar-server.ps1 -Server root@192.168.1.60
#            powershell -File tools\naar-server.ps1 -Server root@<ip> -Doel /opt/vitalytics
# Vereist:   OpenSSH-client (standaard in Windows 10/11) en SSH-toegang tot de CT.
#            Eerste keer verbinden? ssh root@<ip> en accepteer de hostkey.
param(
  [Parameter(Mandatory = $true)][string]$Server,   # bijv. root@192.168.1.60
  [string]$Doel = "/opt/vitalytics",               # map op de server
  [string]$SshPoort = "22"
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

$tar = Join-Path $env:TEMP "vitalytics-deploy.tar.gz"
if (Test-Path $tar) { Remove-Item $tar -Force }

Write-Host "1/3 Archief maken (zonder venv, data, caches — je data blijft op de server)..."
tar -czf $tar --exclude=venv --exclude=.venv --exclude=__pycache__ --exclude=.git --exclude=data --exclude=*.tar.gz -C $Root .

Write-Host "2/3 Uploaden naar ${Server}:$Doel ..."
scp -P $SshPoort $tar "${Server}:/tmp/vitalytics-deploy.tar.gz"

Write-Host "3/3 Uitpakken en installeren op de server..."
ssh -p $SshPoort $Server "mkdir -p '$Doel' && tar -xzf /tmp/vitalytics-deploy.tar.gz -C '$Doel' && rm /tmp/vitalytics-deploy.tar.gz && bash '$Doel/tools/debian-installeer.sh'"

Remove-Item $tar -Force -ErrorAction SilentlyContinue
Write-Host ""
Write-Host "Klaar. Open http://<ip-van-de-ct>:5055 in je browser."
Write-Host "Opnieuw deployen na wijzigingen? Draai dit script opnieuw; je data in data/ blijft staan."