# Vitalytics

Lokale webapplicatie die je Garmin-gezondheidsdata combineert met een
maaltijdlogboek en daar persoonlijk trainings- en voedingsadvies uit maakt.

**Alles draait op je eigen machine:** SQLite voor data, geen cloud, geen
abonnement, geen data naar derden.

## Snel starten

1. Vereisten: Python 3.10+ (getest met 3.14)
2. `python -m pip install -r requirements.txt` (installeert Flask + waitress)
3. `python app.py` (of dubbelklik `run.bat` — die host de app op je thuisnetwerk)
4. Open http://127.0.0.1:5055
5. Log maaltijden op de Maaltijden-pagina en sync je Garmin-data via het dashboard.

## Hosten op een mini pc (bijv. Beelink met Proxmox)

### Linux — Proxmox CT met Debian (aanbevolen)

**CT aanmaken (Proxmox-web-UI):**
1. Datacenter → opslag met templates → *CT Templates* → **Debian 12** downloaden.
2. *Create CT*: hostname bijv. `vitalytics`, vink **Unprivileged container** aan,
   wachtwoord/ssh-key, template Debian 12.
3. Resources: 2 kernen, **2 GB RAM**, **8 GB disk**, 1 netwerkkaart (DHCP of vast
   IP — geef liever een vaste IP/DHCP-lease zodat het adresje blijft).
4. Start de CT en log in als root.

**App erop zetten (vanuit Windows):**

```powershell
powershell -File tools\naar-server.ps1 -Server root@<ip-van-ct>
```

Dit maakt een tar (zonder `venv`, `data`, caches — je data blijft op de CT),
stuurt hem over en draait het installatiescript. Handmatig kan ook: zet de
projectmap op de CT (bijv. `/opt/vitalytics`) en draai daar:

```bash
bash tools/debian-installeer.sh
```

Het installatiescript: installeert Python3 + venv, zet de tijdzone op
Europe/Amsterdam, maakt een systeemgebruiker `vitalytics` aan (de service
**draait niet als root**), bouwt een virtualenv met alle dependencies (flask,
**waitress**, garminconnect), registreert een geharde **systemd-service**
(`vitalytics`) die bij het opstarten van de CT meekomt en bij een crash
herstart (Restart=always), en controleert daarna of de app reageert. De app
bindt op `0.0.0.0`, poort `5055` (wijzig via `VITALYTICS_PORT=...` vóór het
script).

**Na een update** (nieuwe code erop zetten met hetzelfde
`naar-server.ps1`-script, of handmatig): `bash tools/debian-update.sh` —
ververset de dependencies en herstart de service.

**Bereikbaar**: `http://<ct-ip>:5055` — logs via `journalctl -u vitalytics -f`.
Geef de CT een vaste IP (DHCP-lease of statisch) zodat het adresje blijft. In
 een standaard Debian-CT staat geen firewall aan; gebruik je de
Proxmox-firewall op de CT, sta dan poort `5055/tcp` toe.

**Ollama/AI**: draai Ollama op de Proxmox-host of in een aparte VM/CT, en zet
in Instellingen → AI-advies de **API-basis-URL** op
`http://<ip-van-ollama>:11434`. Zonder AI werkt de regelengine gewoon.

**Backups**: een Proxmox CT-backup (vzdump) pakt de hele CT inclusief
`data/` (database, Garmin-tokens, instellingen) mee.

### Windows (rechtstreeks op de pc)

1. `python -m pip install -r requirements.txt` — installeert ook **waitress**
   (productie-server; de Flask dev-server is alleen de fallback).
2. Start via **`run.bat`**: zet `VITALYTICS_HOST=0.0.0.0` en houdt de app
   draaiend met automatische herstart; de adresjes worden geprint (poort via
   `VITALYTICS_PORT`).
3. **Windows Firewall**: bij de eerste start *Toestaan* voor particuliere netwerken.
4. **Autostart bij inloggen**: eenmalig `tools\installeer-autostart.bat`
   (verwijderen: `tools\verwijder-autostart.bat`).

### Beide — over HTTP

De service worker/PWA-installatie vereist HTTPS of localhost — via het LAN
werkt de app gewoon in de browser, maar zonder offline-modus en *App
installeren*. HTTPS? Zet een reverse-proxy (bijv. Caddy/nginx) voor de app.

**Accounts**: de app werkt met accounts (beheer via Instellingen). Het eerste
account maak je bij de eerste start. Zet niets door naar internet (geen
port-forwarding) — de app is alleen bedoeld voor je eigen thuisnetwerk.

**Demo-account**: zodra er een echt account bestaat, maakt de app bij het
starten automatisch account **`demo`** (wachtwoord `demo`) aan. Dat account kan
alles **bekijken** — dashboard, activiteiten, schema, advies — maar niets
wijzigen **of exporteren**: de server weigert alle mutaties én de
CSV/JSON-download (403), en knoppen/velden zijn in de UI inert. Op
Instellingen ziet het demo-account alleen het kaartje **Gebruikers & inloggen**.
Handig om het systeem te demonstreren. Let op: wie demo/demo kent,
kan je data **lezen**. Verwijder je het demo-account, dan komt het bij de
volgende herstart weer terug; geef het via Instellingen een ander wachtwoord
als je het wilt houden maar afschermen.

## UI: Material Design 3 & PWA

De interface volgt **Material Design 3**: design-tokens voor kleur (licht én donker
via `prefers-color-scheme`), 4pt-spacing-raster, M3-componenten (navigation
drawer, cards, chips, gevulde tekstvelden met zwevende labels, snackbar) en
de M3-vormtaal (afgeronde hoeken, pill-knoppen).

- **Desktop-first & PWA**: navigation drawer (256 px) op desktop, compacte
  icon-rail (80 px) op smalle schermen en op telefoons (≤ 767 px) een
  navigatiebalk onderaan zoals in mobiele apps (labels onder de iconen,
  rekening met de iOS safe-area). Installeren via Chrome/Edge → *App
  installeren* of iOS Safari → *Zet op beginscherm*. De service worker
  (`/sw.js`) cachet de app-shell, zodat de UI ook offline werkt (live data
  vereist uiteraard de server).
- **Lettertype**: de UI vraagt eerst om **Google Sans** (aanwezig op veel
  Android/Google-apparaten) en valt terug op *Outfit* via Google Fonts — het
  dichtstbijzijnde openbaar beschikbare alternatief, want Google Sans zelf is
  niet publiek te verspreiden.
- **Iconen**: `tools/gen_icons.py` genereert de PWA-iconen (pure stdlib).
- Tip bij het aanpassen van CSS/JS: verhoog `CACHE` in `static/sw.js` zodat
  clients de nieuwe bestanden ophalen.

## Gegevensbronnen

| Bron | Hoe |
|---|---|
| Garmin CSV-export | Instellingen → CSV-import (kolommen worden automatisch herkend: stappen, slaap, gewicht, HRV, rust-HF, ...) |
| Live Garmin-sync | Instellingen → **Verbinden met 2FA**: e-mail/wachtwoord + code uit je Garmin-app, sms of e-mail. Tokens worden daarna lokaal bewaard, dus **Nu syncen** werkt verder zonder 2FA. Automatisch: **elk heel uur op het uur** (achtergrondthread in de server, ook als niemand de app open heeft) én bij het openen van de app — maximaal één keer per half uur en alleen als Garmin verbonden is |
| Eigen data exporteren | Instellingen → Gegevens exporteren: metingen/maaltijden als CSV of alles als JSON-backup |

## Hoe het advies werkt

De ingebouwde **regelengine** rekent op basis van je data:

- **Trainingsklaarheid (0-100)** uit HRV-trend t.o.v. je basislijn, slaapduur,
  rusthartslag en stressniveau; daaruit volgt het trainingstype van vandaag
  (herstel → zone 2 → tempo-intervallen → zware sessie).
- **Kcal- en macrodoelen** via Mifflin-St Jeor (BMR) x activiteitsfactor uit je
  stappengemiddelde, gecorrigeerd voor je doel (afvallen/presteren/aankomen),
  verminderd met wat je vandaag al gegeten hebt.
- **Coachtips en waarschuwingen** bij afwijkende waarden.

Elke adviesgeneratie wordt gelogd in `data/coach.db` en is terug te lezen op de
Advies-pagina.

## Architectuur

```
app.py                  Flask-routes en paginaweergave
core/
  store.py              SQLite-opslag (metingen, maaltijden, advies, instellingen)
  garmin_client.py      Garmin Connect-sync, tolerante CSV-import, demodata
  advisor.py            Regelgebaseerde adviesengine
  meal_vision.py        AI-schatting van voedingswaarden via maaltijdfoto of omschrijving
  ai_utils.py           (inactieve hook) Ollama HTTP-hulpjes
templates/, static/     MD3-UI (tokens in style.css), vanilla JS, inline SVG-sparklines
static/sw.js            Service worker (offline app-shell)
static/icons/           PWA-iconen (gegenereerd door tools/gen_icons.py)
data/                   coach.db + uploads/ (wordt automatisch aangemaakt)
```

De Ollama/AI-modules staan bewust losgekoppeld van de actieve app (geen imports
van `app.py`). Wil je later toch lokale AI voor maaltijdfoto's of LLM-advies,
dan zijn de bouwstenen er al.

## Beveiliging & privacy

- **Inlog + accounts**: de app is achter een login (accounts via Instellingen);
  standaard bindt de server op `127.0.0.1`, voor het thuisnetwerk zet
  `run.bat`/het installatiescript `VITALYTICS_HOST=0.0.0.0`. Host alleen op een
  vertrouwd thuisnetwerk en zet niets door naar internet (geen port-forwarding).
- Je Garmin-wachtwoord wordt **onversleuteld** in de lokale database opgeslagen;
  gebruik dit alleen op je eigen pc.
- Maaltijdfoto's worden **niet opgeslagen**: ze gaan alleen tijdelijk naar de
  AI-analyse (bestaande foto's in `data/uploads/` blijven gewoon zichtbaar).

## Probleemoplossing

- **Garmin-sync faalt** → de unofficial API verandert regelmatig; werk bij met
  `pip install -U garminconnect` of gebruik de CSV-export. Bij 2FA werkt de
  automatische login vaak niet; gebruik dan de CSV-import.
- **CSV herkent kolommen niet** → import werkt met de standaard Garmin-export;
  eigen CSV's moeten een datumkolom bevatten en herkenbare kolomnamen
  (steps/stappen, weight/gewicht, hrv, ...).
- **Poort bezet** → start met een andere poort: `set VITALYTICS_PORT=5056` (in de
  bat, of als omgevingsvariabele).