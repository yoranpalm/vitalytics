# AGENTS.md — Vitalytics

Lokale gezondheidscoach: Garmin-data, maaltijdlogboek en persoonlijk
trainings-/voedingsadvies. Flask + SQLite + vanilla JS, geen build-stap en
geen frontend-framework. Alles in het Nederlands (code, UI en comments).

## Snel starten

- Lokaal draaien: `run.bat` (host 0.0.0.0, poort 5055) of `python app.py`
- Testen: geen testframework. Verifieer wijzigingen met
  `python -c "import app"` en `node --check static/app.js`,
  plus Jinja: `env.parse(open("templates/<x>.html", encoding="utf-8").read())`
- Deployen naar de Proxmox-CT:
  `powershell -File tools\naar-server.ps1 -Server root@<ip-van-de-CT>`
  (archiveert zonder `data/` — de database blijft op de CT — en herstart
  de systemd-service). Werkt ook in Windows PowerShell 5.1: houd dit script
  ASCII-only en gebruik geen `&&`.

## Architectuur

- `app.py` — alle Flask-routes (~40), Jinja-filters (`datum_tijd`, enz.),
  login (`before_request` dwingt login af; session["gebruiker"]),
  Garmin-sync-route en een auto-sync met throttle.
- `core/store.py` — SQLite (`data/coach.db`). Migraties staan in `init_db`:
  idempotent via PRAGMA-checks; voeg nieuwe kolommen/zaken DAAR toe, niet
  los in routes.
- `core/advisor.py` — regelengine (Mifflin-St Jeor, readyheid) + AI-advies.
  De regelengine is leidend: AI levert tekst, cijfers komen uit de engine.
- `core/health_summary.py` — dashboard-analyse; `core/schema_advisor.py` —
  trainingschema-advies; `core/meal_vision.py` — maaltijdfoto's;
  `core/ai_utils.py` — providerroutering (Ollama lokaal of Gemini/
  OpenAI-compatibel cloud).
- `templates/` + `static/` — server-rendered Jinja + één JS-bestand
  (`app.js`, vanilla). Geen frameworks, geen CDN's.

## Belangrijke regels en conventies

1. **Cache-bumpen**: bij elke wijziging in `static/style.css` of
   `static/app.js` de query-params verhogen (`style.css?v=N` in base.html én
   login.html, `app.js?v=N` in base.html) én `CACHE`/`VERSION` in
   `static/sw.js`. CSS/JS zijn network-first, HTML ook; zonder bump blijven
   PWA's soms oudere assets zien.
2. **Mobiel-first afronden**: alle mobiele stijlen staan in twee media
   queries aan het einde van `style.css` (`max-width: 767px` = telefoon,
   `max-width: 559px` = compact). Fontstappen lopen via `--fs-*`, ruimte via
   `--sp-*` (4pt-raster). Bepaalde regels staan bewust NÁ de
   componentstijlen omdat gelijke specificiteit anders terugverliest
   (zie de comments over `.card.accordion` en `.samenvatting`).
3. **Beweging**: subtiele M3-animaties (fade-up 0,32s, staggered reveal via
   `data-reveal`, voortgangsbalken `grow-x`). Alles moet uit staan bij
   `prefers-reduced-motion` (centraal blok in style.css). De
   paginawissel-animatie is JS-gestuurd (`.main.page-uit` + 140 ms delay) —
   Geen cross-document View Transitions: die slaan browsers over bij
   bfcache; ruim bij `pageshow` de class weer op.
4. **AI-privacy**: gaat data naar een cloudprovider (`ai_utils.use_api()`),
   dan geanonimiseerd: `advisor.rel_dag` voor relatieve dagnotatie,
   activiteitentype i.p.v. naam, en fotot's zonder EXIF
   (`meal_vision._exif_loos`, Pillow). Lokale Ollama krijgt volledige data.
   De API-sleutel zelf identificeert het account bij de aanbieder — dat kan
   niet weg.
5. **Accounts**: weekdoelen, schema's en schema-advies zijn gekoppeld aan
   `(week, gebruiker)` — geef `session.get("gebruiker")` door aan
   `store.get_/save_training_plan` en `training_tips`. Metingen, maaltijden,
   adviezen en instellingen zijn nog instantie-breed (uitbreiden? zelfde
   aanpak). Het auto-aangemaakte account `demo` is read-only en telt niet
   als eigenaar van legacy-data.
6. **Datums in prompts**: nooit absolute data naar een cloudprovider —
   gebruik `advisor.rel_dag`. UI-toont op mobiel numerieke datums
   (`.datum-kort`/`.datum-lang`, gekozen door CSS).
7. **Demo-modus**: account "demo" is alleen-bekijken; de server weigert alle
   mutaties (`before_request`), de UI dimt knoppen.
8. **Regeleindes**: `*.py`/`*.js`/`*.css` zijn LF (zie `.gitattributes`);
   genormaliseer bestanden vóór het bewerken als een multi-line edit
   faalt (mixte CRLF-bestanden komen voor).

## Bekende valkuilen

- `sw.js` draait als PWA-cache op telefoons: na deploys kan een keer
  volledig sluiten/heropenen nodig zijn.
- De gezondheidsanalyse is op mobiel standaard ingeklapt (inline-script in
  `dashboard.html`, matchMedia 767px).
- Jinja-filters die HTML teruggeven (zoals `datum_tijd`) geven `Markup`
  terug; gewone filters zonder `|safe` escapen.
- PowerShell 5.1 leest bestanden zonder BOM als ANSI: geen em-dashes of
  unicode in `.ps1`-bestanden, en geen `&&` (dat is pwsh 7).

## Deploy

- Productie: Proxmox CT (hostnaam `vitalytics`, zie `tools/naar-server.ps1`
  voor het adres), systemd-service `vitalytics`, poort 5055. SSH met sleutel;
- `data/` (database, Garmin-tokens, uploads) blijft bij deploys altijd op
  de CT staan — het archief sluit die map uit.
- Alle apparaten moeten hetzelfde adres gebruiken; er draaien geen
  gedeelde databases tussen instanties.
