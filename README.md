# Vitalytics

**Lokale gezondheidscoach** — Vitalytics combineert je Garmin-gezondheidsdata met een
maaltijdlogboek en vertaalt dat naar concreet trainings- en voedingsadvies. Alles draait
op je eigen machine: SQLite als opslag, geen cloud voor je data, geen abonnement, niets
naar derden.

## Functies

- **Dashboard met trainingsklaarheid (0–100)** — berekend uit HRV-trend t.o.v. je
  basislijn, slaapduur, rusthartslag en stressniveau; daaruit volgt het trainingstype
  van de dag (herstel → zone 2 → tempo-intervallen → zware sessie).
- **Live Garmin-sync** — metingen en activiteiten worden automatisch opgehaald: elk heel
  uur via een achtergrondthread (ook als niemand de app open heeft) én bij het openen
  van de app, maximaal één keer per half uur. Na eenmalige 2FA-login blijven de tokens
  lokaal bewaard en werkt "Nu syncen" zonder nieuwe code.
- **CSV-import** — herkent de standaard Garmin-export (stappen, slaap, gewicht, HRV,
  rust-HF, …) en is de fallback als de unofficial API niet meewerkt.
- **Maaltijdlogboek** — met AI-schatting van kcal en macro's uit een maaltijdfoto of
  een omschrijving.
- **Dagadvies** — kcal- en macrodoelen via Mifflin-St Jeor (BMR) × activiteitsfactor uit
  je stappengemiddelde, gecorrigeerd voor je doel (afvallen/presteren/aankomen) en wat
  je vandaag al gegeten hebt; plus coachtips en waarschuwingen bij afwijkende waarden.
- **Weekschema (AI)** — concrete sessie-opbouw per geplande training (kracht, zwemmen,
  enz.) volgens progressieve overbelasting; per week op te vragen, aan te passen en op
  te slaan.
- **Activiteitenanalyse** — regelgebaseerde interpretatie per activiteit (type, belasting,
  been-dag) in dezelfde stijl als de adviesengine.
- **Export** — metingen en maaltijden als CSV, alles als JSON-backup (zonder
  wachtwoorden en API-sleutel).
- **PWA** — installeerbaar op desktop en telefoon; de service worker cachet de
  app-shell voor offline gebruik.

## Hoe het advies werkt

Het advies bestaat uit twee lagen:

1. **Regelengine (altijd actief).** Deterministische, uitlegbare berekeningen:
   HRV-trend, slaap, rust-HF, stappengemiddelden, BMR (Mifflin-St Jeor) en macrodoelen.
   De app is volledig functioneel zonder enige AI-configuratie.
2. **AI-laag (optioneel).** Een taalmodel krijgt je data plus de regelengine-uitkomst
   als feitenkader en levert een onderbouwd advies in JSON, in begrijpelijke taal.
   Faalt de AI (geen verbinding, quota, ontbrekend model), dan valt de app terug op de
   regelengine. De bron van elk advies wordt gelogd en op de Advies-pagina getoond.

AI kan **lokaal** draaien (Ollama, bijv. op de Proxmox-host of een aparte VM/CT via
`http://<ip>:11434`) of via een **OpenAI-compatibele cloud-API** (OpenAI, OpenRouter,
DeepSeek, Gemini). Voor maaltijdfoto's is een vision-model nodig (llava, llama3.2-vision,
qwen2.5vl, gemma3, …).

## Architectuur

```
app.py                  Flask-app: routes, authenticatie, achtergrond-sync (uurthread)
core/
  store.py              SQLite-opslag (metingen, maaltijden, activiteiten, advies,
                        accounts, instellingen) in data/coach.db
  garmin_client.py      Garmin Connect-sync, tolerante CSV-import, demodata
  advisor.py            Dagadvies: AI met regelengine als valback én feitenkader
  activity_analysis.py  Regelgebaseerde analyse per activiteit
  schema_advisor.py     AI-advies bij het weektrainingsschema
  meal_vision.py        AI-schatting van voedingswaarden (foto of omschrijving)
  ai_utils.py           Provider-laag: Ollama (lokaal), OpenAI-compatibel, Gemini
templates/, static/     Material Design 3-UI (tokens, drawer, cards), vanilla JS
static/sw.js            Service worker; CACHE-versie verhogen bij CSS/JS-wijzigingen
tools/                  Deploy- en beheerscripts (Windows + Debian)
data/                   Runtime-data (database, tokens, uploads, sessiesleutel) — niet in git
```

## Installatie

Vereisten: Python 3.10+ (getest met 3.14). Dependencies: Flask, waitress, garminconnect.

### Windows (rechtstreeks op de pc)

1. `python -m pip install -r requirements.txt`
2. Start via **`run.bat`** — host `0.0.0.0`, automatische herstart, log in `data\app.log`.
3. Open `http://127.0.0.1:5055` en maak het eerste account aan. Windows Firewall:
   bij de eerste start *Toestaan* voor particuliere netwerken.
4. Optioneel automatisch starten bij inloggen: `tools\installeer-autostart.bat`
   (verwijderen: `tools\verwijder-autostart.bat`).

### Debian CT op Proxmox (aanbevolen voor 24/7-hosting)

1. CT aanmaken: Debian 12, **unprivileged**, 2 GB RAM, 8 GB disk, vast IP (of DHCP-lease).
2. Deployen vanuit Windows: `powershell -File tools\naar-server.ps1 -Server root@<ip>`
   — of handmatig de projectmap naar bijv. `/opt/vitalytics` kopiëren en daar
   `bash tools/debian-installeer.sh` draaien.
3. Het installatiescript richt in: Python + venv, systeemgebruiker `vitalytics`
   (de service draait **niet** als root), tijdzone Europe/Amsterdam en een geharde
   systemd-service (Restart=always, NoNewPrivileges, PrivateTmp, ProtectSystem=full)
   die bij het booten meekomt.
4. Na een update: nieuwe code erop zetten (zelfde deploy-script) en
   `bash tools/debian-update.sh` draaien — ververst dependencies en herstart de service.

De app is dan bereikbaar op `http://<ct-ip>:5055`. In een standaard Debian-CT staat
geen firewall aan; gebruik je de Proxmox-firewall, sta dan poort `5055/tcp` toe.

### Configuratie

| Variabele | Standaard | Betekenis |
|---|---|---|
| `VITALYTICS_HOST` | `127.0.0.1` | Bind-adres; `run.bat` en het installatiescript zetten `0.0.0.0` |
| `VITALYTICS_PORT` | `5055` | HTTP-poort |

## Gegevensbronnen

| Bron | Hoe |
|---|---|
| Garmin CSV-export | Instellingen → CSV-import; kolommen worden automatisch herkend (steps/stappen, weight/gewicht, hrv, …) |
| Live Garmin-sync | Instellingen → e-mail/wachtwoord + 2FA-code; daarna lokale tokens, automatische sync per uur |
| Eigen data exporteren | Instellingen → metingen/maaltijden als CSV of alles als JSON-backup |

## Accounts

- De app staat achter een login; het **eerste account** maak je bij de eerste start.
- Zodra er een echt account bestaat, maakt de app automatisch een **demo-account**
  aan (`demo`/`demo`) dat alles kan **bekijken** maar niets wijzigen of exporteren
  (server weigert alle mutaties en downloads met 403). Handig voor demonstraties;
  verwijderen of afschermen kan via Instellingen.

## Beveiliging & privacy

- Wachtwoorden van accounts worden gehasht opgeslagen; sessies zijn ondertekend met een
  sleutel in `data/session-secret`.
- Het **Garmin-wachtwoord wordt onversleuteld** in de lokale database bewaard (nodig
  voor herlogin en 2FA). Gebruik de app daarom alleen op je eigen machine.
- Bind de server alleen op `0.0.0.0` op een vertrouwd thuisnetwerk en zet niets door
  naar internet (geen port-forwarding).
- Maaltijdfoto's worden **niet opgeslagen**: ze gaan alleen tijdelijk naar de
  AI-analyse. Kies je een cloud-provider, dan ziet die provider de foto tijdelijk;
  met lokaal Ollama verlaat de foto je netwerk niet.
- Backups: een Proxmox CT-backup (vzdump) omvat de hele CT inclusief `data/`
  (database, Garmin-tokens, instellingen).

## Probleemoplossing

- **Garmin-sync faalt** — de unofficial API verandert regelmatig; werk bij met
  `pip install -U garminconnect` of gebruik de CSV-import. Bij 2FA werkt de automatische
  login niet altijd; dan CSV-import gebruiken.
- **CSV-kolommen niet herkend** — de import vereist een datumkolom en herkenbare
  kolomnamen (steps/stappen, weight/gewicht, hrv, …).
- **Poort bezet** — start met een andere poort via `VITALYTICS_PORT` (bijv. `5056`).
- **Service start niet op de CT** — bekijk `journalctl -u vitalytics -n 50`. Meldt
  systemd "Permission denied" op de working directory, check dan of `/opt/vitalytics`
  (en de mappen erboven) leesbaar is voor de gebruiker `vitalytics`.

## Status

Privéproject, actief in gebruik in het eigen thuisnetwerk. Nog geen openbare licentie.