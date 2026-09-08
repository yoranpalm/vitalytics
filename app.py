"""Vitalytics — lokale webapplicatie (100% lokaal, geen cloud).

- Haalt gezondheidsdata op via Garmin Connect (garminconnect), CSV-export of demodata
- Logt maaltijden (handmatig, via een korte omschrijving of foto)
- Genereert gepersonaliseerd trainings- en voedingsadvies via de regelengine

Start:  python app.py   ->   http://127.0.0.1:5055
"""
import csv
import io
import json
import os
import secrets
import socket
import threading
import time
from datetime import datetime, timedelta

from flask import (Flask, Response, jsonify, redirect, render_template,
                   request, send_from_directory, session)
from markupsafe import Markup

from core import (activity_analysis, advisor, ai_utils, garmin_client,
                  health_summary, meal_vision, schema_advisor, store)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024
app.config["TEMPLATES_AUTO_RELOAD"] = True  # lokale tool: template-wijzigingen direct zien
app.json.ensure_ascii = False

store.init_db()

# hosting: standaard alleen deze pc; voor een mini pc/thuisnetwerk zet
# run.bat VITALYTICS_HOST=0.0.0.0 (poort optioneel via VITALYTICS_PORT)
HOST = os.environ.get("VITALYTICS_HOST", "127.0.0.1")
try:
    PORT = int(os.environ.get("VITALYTICS_PORT", "5055"))
except (TypeError, ValueError):
    PORT = 5055


def _sessie_secret():
    """Sessie-sleutel: eenmalig aangemaakt en bewaard in data/ (blijft geldig)."""
    pad = os.path.join(store.DATA_DIR, "session-secret")
    try:
        with open(pad) as f:
            waarde = f.read().strip()
        if waarde:
            return waarde
    except OSError:
        pass
    waarde = secrets.token_hex(32)
    os.makedirs(store.DATA_DIR, exist_ok=True)
    with open(pad, "w") as f:
        f.write(waarde)
    return waarde


app.secret_key = _sessie_secret()


def _zorg_demo_account():
    """Read-only demo-account (demo/demo) zodat je de app kunt laten zien:
    dat account mag alleen rondkijken, niets wijzigen. Bestaat pas zodra er een
    echt account is (de eerste-start-flow 'maak je eerste account' blijft
    werken) en een bestaand demo-wachtwoord wordt nooit overschreven."""
    if store.aantal_gebruikers() and not store.heeft_gebruiker("demo"):
        store.maak_gebruiker("demo", "demo")


_zorg_demo_account()

# 2FA-loginflow: achtergrondthread; metingen én activiteiten worden direct opgeslagen
def _store_garmin_sync(metric_records, activity_records):
    dagen = sum(1 for r in metric_records if store.upsert_metric(r, replace=True))
    acts = sum(1 for r in activity_records if store.upsert_activity(r))
    store.set_setting("last_sync", store.now())
    store.set_setting("last_sync_ok", store.now())  # alleen bij geslaagde sync
    return dagen, acts


garmin_flow = garmin_client.GarminLoginFlow(on_sync=_store_garmin_sync)


def _recent_sync(minuten):
    """True als er binnen de laatste `minuten` al een sync-poging is geweest."""
    try:
        delta = datetime.now() - datetime.strptime(store.get_setting("last_sync"),
                                                   "%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return False
    return delta < timedelta(minutes=minuten)


# automatische sync: bij het openen van de app (max. 1x per half uur) én elk
# heel uur op het uur via een achtergrondthread — zo wordt de data ook bij-
# gewerkt terwijl niemand de app open heeft staan
AUTO_SYNC_MINUTEN = 30
_auto_sync_lock = threading.Lock()


def _auto_sync_poging():
    """Één automatische Garmin-sync-poging: alleen als de garminconnect-package
    aanwezig is én er e-mail/wachtwoord ingesteld zijn. Elke poging (geslaagd
    of niet) zet last_sync, zodat een falende verbinding niet steeds opnieuw
    probeert. Geeft een resultaat-dict terug."""
    if not garmin_client.garmin_available():
        return {"gesynced": False, "reden": "geen-garminconnect"}
    cfg = store.settings()
    if not (cfg.get("garmin_email") and cfg.get("garmin_password")):
        return {"gesynced": False, "reden": "niet-verbonden"}
    store.set_setting("last_sync", store.now())  # poging telt mee
    try:
        metrics, activities = garmin_client.sync_all(
            days=int(_float(cfg.get("sync_days")) or 7),
            email=cfg.get("garmin_email") or None,
            password=cfg.get("garmin_password") or None)
    except Exception as exc:
        return {"gesynced": False, "reden": "sync-fout", "fout": str(exc)}
    dagen = sum(1 for rec in metrics if store.upsert_metric(rec, replace=True))
    acts = sum(1 for rec in activities if store.upsert_activity(rec))
    store.set_setting("last_sync_ok", store.now())  # alleen bij geslaagde poging
    return {"gesynced": True, "dagen": dagen, "activiteiten": acts}


def _uur_sync_loop():
    """Achtergrondthread: elke keer precies op het hele uur (xx:00) een
    Garmin-sync. Draait mee met het serverproces (daemon)."""
    while True:
        nu = datetime.now()
        volgende = nu.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        time.sleep(max(1, (volgende - nu).total_seconds()))
        try:
            if _recent_sync(AUTO_SYNC_MINUTEN):
                continue  # er was net al een poging (bijv. via paginalading)
            with _auto_sync_lock:
                if _recent_sync(AUTO_SYNC_MINUTEN):
                    continue
                res = _auto_sync_poging()
            if res["gesynced"]:
                print(f"[garmin] uursync {datetime.now():%H:%M}: "
                      f"{res['dagen']} dag(en) metingen, "
                      f"{res['activiteiten']} activiteit(en)")
            elif res.get("reden") == "sync-fout":
                print(f"[garmin] uursync mislukt: {res.get('fout')}")
        except Exception as exc:
            print(f"[garmin] uursync onverwachte fout: {exc}")


_uur_sync_thread = threading.Thread(target=_uur_sync_loop, daemon=True,
                                    name="garmin-uursync")
_uur_sync_thread.start()


def _float(value):
    try:
        if value in ("", None):
            return None
        return round(float(str(value).replace(",", ".")), 2)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- pagina's

# ------------------------------------------------------- inloggen

@app.before_request
def _vereist_login():
    """Alles achter een login, behalve het inlogscherm en statische bestanden."""
    if session.get("gebruiker"):
        if session.get("demo"):
            # demo-account: alleen bekijken — de server dwingt dit af, ongeacht
            # wat de UI doet (knoppen, API-calls, formulieren). Ook export (GET!)
            # zit achter slot en grendel: CSV/JSON bevat de volledige data.
            export = request.path.startswith("/api/export/")
            if export or request.method not in ("GET", "HEAD", "OPTIONS"):
                if request.path.startswith("/api/"):
                    return jsonify({"error": "Demo-account: alleen bekijken"}), 403
                return redirect("/")
        return None
    if (request.endpoint or "") in ("login", "uitloggen", "static", "favicon", "sw_js"):
        return None
    if request.path.startswith("/api/"):
        return jsonify({"error": "Niet ingelogd"}), 401
    return redirect("/login")


@app.route("/login", methods=["GET", "POST"])
def login():
    fout = None
    geen = not store.aantal_gebruikers()
    if request.method == "POST":
        gebruiker = (request.form.get("gebruiker") or "").strip()
        wachtwoord = request.form.get("wachtwoord") or ""
        if geen:
            # eerste account: met het formulier direct aanmaken en inloggen
            if len(gebruiker) < 3 or len(wachtwoord) < 4:
                fout = "Kies een gebruikersnaam (min. 3 tekens) en een wachtwoord (min. 4 tekens)."
            else:
                store.maak_gebruiker(gebruiker, wachtwoord)
                session["gebruiker"] = gebruiker
                return redirect("/")
        else:
            account = store.controleer_login(gebruiker, wachtwoord)
            if account:
                session["gebruiker"] = account["username"]
                if account["username"] == "demo":
                    session["demo"] = True  # read-only: alleen rondkijken
                return redirect("/")
            fout = "Onjuiste logingegevens."
    return render_template("login.html", fout=fout, geen_gebruikers=geen)


@app.route("/uitloggen")
def uitloggen():
    session.clear()
    return redirect("/login")


def _sync_ts_leesbaar(ts):
    """Laatste geslaagde sync kort leesbaar: 'vandaag 21:00', 'gisteren 21:00'
    of '8 sep · 21:00'. None bij geen/ongeldige waarde."""
    if not ts:
        return None
    try:
        d = datetime.strptime(str(ts)[:16], "%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return None
    vandaag = store.today()
    if str(ts)[:10] == vandaag:
        return f"vandaag {d:%H:%M}"
    gisteren = (datetime.strptime(vandaag, "%Y-%m-%d")
                 - timedelta(days=1)).strftime("%Y-%m-%d")
    if str(ts)[:10] == gisteren:
        return f"gisteren {d:%H:%M}"
    return f"{d.day} {_MAANDEN_KORT[d.month - 1]} · {d:%H:%M}"


@app.route("/")
def dashboard():
    metrics = store.get_metrics(30)
    meals_today = store.get_meals_today()
    totals = {k: round(sum(m[k] or 0 for m in meals_today), 1)
              for k in ("kcal", "protein", "carbs", "fat")}
    last_act = None
    acts = store.get_activities(1)
    if acts:
        last_act = {"rec": acts[0],
                    "an": activity_analysis.analyse_activity(
                        acts[0], [], {"age": store.get_setting("age")})}
    return render_template("dashboard.html", cards=_cards(metrics),
                           meals_today=meals_today, totals=totals,
                           latest=store.latest_advice(), last_act=last_act,
                           laatste_sync=_sync_ts_leesbaar(
                               store.get_setting("last_sync_ok")),
                           samenvatting=health_summary.huidige())


@app.route("/meals")
def meals():
    rows = store.get_meals(100)
    vandaag = store.today()
    dagen = []
    for m in rows:  # gesorteerd op tijdstip, dus dezelfde dag ligt bij elkaar
        dag = (m.get("ts") or vandaag)[:10]
        if not dagen or dagen[-1]["datum"] != dag:
            dagen.append({"datum": dag, "label": _dag_label(dag, vandaag),
                          "label_kort": _dag_label_kort(dag, vandaag),
                          "maaltijden": [],
                          "totaal": {"kcal": 0, "protein": 0, "carbs": 0, "fat": 0}})
        g = dagen[-1]
        g["maaltijden"].append(m)
        for k in ("kcal", "protein", "carbs", "fat"):
            g["totaal"][k] += m[k] or 0
    return render_template("meals.html", dagen=dagen, vandaag=vandaag,
                           aantal=len(rows))


def _dag_label(dag, vandaag):
    """Leesbare dagkop: 'Vandaag', 'Gisteren' of 'dinsdag 8 september'."""
    if dag == vandaag:
        return "Vandaag"
    gisteren = (datetime.strptime(vandaag, "%Y-%m-%d")
                 - timedelta(days=1)).strftime("%Y-%m-%d")
    if dag == gisteren:
        return "Gisteren"
    try:
        d = datetime.strptime(dag, "%Y-%m-%d")
    except (TypeError, ValueError):
        return dag
    label = f"{MEAL_DAGEN[d.weekday()]} {d.day} {SCHEMA_MONTHS[d.month - 1]}"
    if d.year != datetime.now().year:
        label += f" {d.year}"
    return label


def _dag_label_kort(dag, vandaag):
    """Korte dagkop voor mobiel: 'Vandaag', 'Gisteren' of 'di 08-09'."""
    if dag == vandaag:
        return "Vandaag"
    gisteren = (datetime.strptime(vandaag, "%Y-%m-%d")
                 - timedelta(days=1)).strftime("%Y-%m-%d")
    if dag == gisteren:
        return "Gisteren"
    try:
        d = datetime.strptime(dag, "%Y-%m-%d")
    except (TypeError, ValueError):
        return dag
    return f"{MEAL_DAGEN[d.weekday()][:2]} {d.day:02d}-{d.month:02d}"


def _meal_ts(datum):
    """'jjjj-mm-dd' -> maaltijdtijdstip: vandaag = nu, eerdere dag = die dag
    12:00. None bij een ongeldige of toekomstige datum."""
    if not datum:
        return store.now()
    try:
        dag = datetime.strptime(str(datum), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    if dag > datetime.now().date():
        return None
    return store.now() if dag == datetime.now().date() else f"{dag} 12:00"


@app.route("/activities")
def activities_page():
    activities = store.get_activities(200)
    today = store.today()
    week_start = (datetime.strptime(today, "%Y-%m-%d").date()
                  - timedelta(days=6)).strftime("%Y-%m-%d")
    profile = {"age": store.get_setting("age")}

    pace_by_type = {}
    for a in activities:
        if a.get("type") and a.get("distance_m") and a.get("duration_s"):
            pace_by_type.setdefault(a["type"], []).append(
                (a["duration_s"] / (a["distance_m"] / 1000), a["activity_id"]))

    rows, week = [], {"aantal": 0, "duur_s": 0, "afstand_m": 0, "kcal": 0}
    for a in activities:
        peers = [pace for pace, aid in pace_by_type.get(a.get("type"), [])
                 if aid != a["activity_id"]]
        rows.append({"rec": a,
                     "an": activity_analysis.analyse_activity(a, peers, profile)})
        if (a.get("start_time") or "")[:10] >= week_start:
            week["aantal"] += 1
            week["duur_s"] += a.get("duration_s") or 0
            week["afstand_m"] += a.get("distance_m") or 0
            week["kcal"] += a.get("calories") or 0

    week["duur_fmt"] = activity_analysis.fmt_duration(week["duur_s"])
    week["afstand_km"] = f"{week['afstand_m'] / 1000:.1f}".replace(".", ",")
    return render_template("activities.html", rows=rows, week=week)


# ------------------------------------------------------- trainingsschema

SCHEMA_DAYS = ["Maandag", "Dinsdag", "Woensdag", "Donderdag", "Vrijdag",
               "Zaterdag", "Zondag"]
SCHEMA_MONTHS = ["januari", "februari", "maart", "april", "mei", "juni", "juli",
                 "augustus", "september", "oktober", "november", "december"]
_MAANDEN_KORT = ["jan", "feb", "mrt", "apr", "mei", "jun", "jul",
                 "aug", "sep", "okt", "nov", "dec"]
MEAL_DAGEN = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag",
              "zaterdag", "zondag"]


@app.template_filter("datum")
def _filter_datum(waarde):
    """Datum als dag-maand-jaar: '7 september 2026'."""
    try:
        d = datetime.strptime((str(waarde or ""))[:10], "%Y-%m-%d")
    except (TypeError, ValueError):
        return str(waarde or "")
    return f"{d.day} {SCHEMA_MONTHS[d.month - 1]} {d.year}"


@app.template_filter("datum_tijd")
def _filter_datum_tijd(waarde):
    """Datum + tijd in twee varianten: lang '7 september 2026 · 16:59' en kort
    '07-09-2026 · 16:59' — CSS toont op telefoons de korte (mobiel-only kan
    geen Jinja, dus beide renderen en per breakpoint tonen)."""
    try:
        d = datetime.strptime((str(waarde or ""))[:16], "%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return str(waarde or "")
    lang = f"{d.day} {SCHEMA_MONTHS[d.month - 1]} {d.year}"
    kort = f"{d.day:02d}-{d.month:02d}-{d.year}"
    return Markup(f'<span class="datum-lang">{lang}</span>'
                  f'<span class="datum-kort">{kort}</span>'
                  f" · {d.hour:02d}:{d.minute:02d}")


def _week_key(day):
    iso = day.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _parse_week(key):
    """'2026-W37' -> datum van de maandag; None bij ongeldige input."""
    try:
        return datetime.strptime(f"{key}-1", "%G-W%V-%u").date()
    except (TypeError, ValueError):
        return None


def schema_week_meta(week):
    monday = _parse_week(week) or _parse_week(_week_key(datetime.now().date()))
    sunday = monday + timedelta(days=6)
    iso = monday.isocalendar()
    if monday.month == sunday.month:
        bereik = f"{monday.day} – {sunday.day} {SCHEMA_MONTHS[sunday.month - 1]} {sunday.year}"
    else:
        bereik = (f"{monday.day} {SCHEMA_MONTHS[monday.month - 1]} – "
                  f"{sunday.day} {SCHEMA_MONTHS[sunday.month - 1]} {sunday.year}")
    return {"key": _week_key(monday), "nummer": iso[1], "bereik": bereik,
            "prev": _week_key(monday - timedelta(days=7)),
            "next": _week_key(monday + timedelta(days=7)),
            "is_current": _week_key(datetime.now().date()) == _week_key(monday),
            "today_weekday": datetime.now().isoweekday() if
            _week_key(datetime.now().date()) == _week_key(monday) else None}


def _match_weekdag(label):
    """Zet een dag-label uit het AI-advies om naar een ISO-weekdag (1–7),
    tolerant voor voluit ("maandag"), afkorting ("ma") en omringende tekst."""
    s = str(label or "").strip().lower()
    if not s:
        return None
    for i, dag in enumerate(SCHEMA_DAYS, start=1):
        dl = dag.lower()
        if dl in s or s in dl:
            return i
    return None


def _open_tip_index(tips, today_weekday):
    """Welke dag in het AI-advies standaard uitgeklapt hoort te zijn: het advies
    van vandaag; heeft vandaag geen advies (rustdag), dan het eerstvolgende
    advies dat nog komt. Zijn alle adviesdagen voorbij, of bekijk je een andere
    week, dan staat er niets vanzelf open."""
    if not tips or today_weekday is None:
        return None
    per_dag = (tips.get("payload") or {}).get("per_dag") or []
    weekdagen = {}
    for i, item in enumerate(per_dag):
        wd = _match_weekdag((item or {}).get("dag"))
        if wd:
            weekdagen[i] = wd
    for i, wd in weekdagen.items():
        if wd == today_weekday:
            return i
    later = [i for i, wd in weekdagen.items() if wd > today_weekday]
    if later:
        return min(later, key=lambda i: weekdagen[i])
    return None


@app.route("/schema")
def schema_page():
    week = request.args.get("week") or _week_key(datetime.now().date())
    if not _parse_week(week):
        week = _week_key(datetime.now().date())
    gebruiker = session.get("gebruiker") or ""
    plan = store.get_training_plan(week, gebruiker)
    tips = store.get_training_tips(plan["week"], gebruiker)
    meta = schema_week_meta(week)
    return render_template("schema.html", plan=plan, days=SCHEMA_DAYS,
                           meta=meta, tips=tips,
                           open_tip=_open_tip_index(tips, meta["today_weekday"]))


@app.route("/api/schema/save", methods=["POST"])
def api_schema_save():
    data = request.get_json(silent=True) or {}
    week = str(data.get("week") or "")
    if not _parse_week(week):
        return jsonify({"error": "Onbekende week"}), 400
    goal = data.get("sessions_goal")
    try:
        goal = int(goal) if goal not in (None, "") else None
    except (TypeError, ValueError):
        goal = None
    if goal is not None and not 0 <= goal <= 21:
        goal = None
    entries = data.get("entries") if isinstance(data.get("entries"), list) else []
    saved = store.save_training_plan(week, goal, entries, session.get("gebruiker") or "")
    return jsonify({"ok": True, "week": week, "opgeslagen": saved})


@app.route("/api/schema/advice", methods=["POST"])
def api_schema_advice():
    """AI-advies bij het weekschema: sessie-opbouw en progressie per training."""
    data = request.get_json(silent=True) or {}
    week = str(data.get("week") or "")
    if not _parse_week(week):
        return jsonify({"error": "Onbekende week"}), 400
    try:
        payload, source = schema_advisor.generate(week, session.get("gebruiker") or "")
    except Exception as exc:
        return jsonify({"error": f"AI-advies mislukt: {exc}"}), 503
    store.save_training_tips(week, payload, source, session.get("gebruiker") or "")
    return jsonify({"ok": True, "week": week})


@app.route("/advice")
def advice_page():
    return render_template("advice.html", history=store.get_advice(20))


@app.route("/settings")
def settings_page():
    return render_template("settings.html", s=store.settings(),
                           garmin_lib=garmin_client.garmin_available(),
                           models=ai_utils.ollama_models())


@app.route("/uploads/<path:filename>")
def uploads(filename):
    return send_from_directory(store.UPLOAD_DIR, filename)


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(os.path.join(app.static_folder, "icons"),
                               "favicon.ico", mimetype="image/x-icon")


@app.route("/manifest.webmanifest")
def manifest():
    """PWA-manifest op root-scope zodat de app installeerbaar is."""
    payload = {
        "name": "Vitalytics",
        "short_name": "Vitalytics",
        "description": "Lokale gezondheidscoach: Garmin-data, maaltijdlogboek en persoonlijk advies.",
        "lang": "nl",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait-primary",
        "background_color": "#11141a",
        "theme_color": "#11141a",
        "icons": [
            {"src": "/static/icons/icon-192.png", "sizes": "192x192",
             "type": "image/png", "purpose": "any"},
            {"src": "/static/icons/icon-512.png", "sizes": "512x512",
             "type": "image/png", "purpose": "any"},
            {"src": "/static/icons/icon-maskable-512.png", "sizes": "512x512",
             "type": "image/png", "purpose": "maskable"},
        ],
    }
    return app.response_class(json.dumps(payload), mimetype="application/manifest+json")


@app.route("/sw.js")
def sw_js():
    """Service worker moet op root-scope staan (dus niet onder /static)."""
    return send_from_directory(app.static_folder, "sw.js", mimetype="text/javascript")


# ---------------------------------------------------------------- api

@app.route("/api/health")
def api_health():
    models = ai_utils.ollama_models()
    return jsonify({"ok": True, "db": store.DB_PATH,
                    "garmin_lib": garmin_client.garmin_available(),
                    "ollama": bool(models), "models": models,
                    "model_advice": store.get_setting("model_advice"),
                    "ai_api": ai_utils.use_api(),
                    "ai_bron": ai_utils.active_source()})


@app.route("/api/settings", methods=["POST"])
def api_settings():
    data = request.get_json(force=True, silent=True) or {}
    allowed = ("age", "sex", "height_cm", "weight_kg", "goal", "step_goal", "sync_days",
               "garmin_email", "garmin_password", "model_advice",
               "ai_provider", "ai_api_key", "ai_base_url", "ai_model")
    saved = []
    for key in allowed:
        if key not in data:
            continue
        value = data[key]
        if key in ("age", "height_cm", "weight_kg", "sync_days", "step_goal"):
            value = _float(value)
            if value is None:
                continue
        store.set_setting(key, value)
        saved.append(key)
    return jsonify({"ok": True, "opgeslagen": saved})


@app.route("/api/gebruikers", methods=["GET"])
def api_gebruikers():
    return jsonify(store.gebruikers())


@app.route("/api/gebruikers", methods=["POST"])
def api_gebruiker_opslaan():
    """Account aanmaken; bestaat de naam al, dan wordt het wachtwoord vernieuwd."""
    data = request.get_json(force=True, silent=True) or {}
    gebruiker = (data.get("gebruiker") or "").strip()
    wachtwoord = data.get("wachtwoord") or ""
    if len(gebruiker) < 3:
        return jsonify({"error": "Gebruikersnaam: minimaal 3 tekens"}), 400
    if len(wachtwoord) < 4:
        return jsonify({"error": "Wachtwoord: minimaal 4 tekens"}), 400
    store.maak_gebruiker(gebruiker, wachtwoord)
    return jsonify({"ok": True})


@app.route("/api/gebruikers/<int:user_id>", methods=["DELETE"])
def api_gebruiker_verwijder(user_id):
    namen = {u["id"]: u["username"] for u in store.gebruikers()}
    if user_id not in namen:
        return jsonify({"error": "Account niet gevonden"}), 404
    if namen[user_id] == session.get("gebruiker"):
        return jsonify({"error": "Je kunt je eigen account niet verwijderen"}), 400
    if store.aantal_gebruikers() <= 1:
        return jsonify({"error": "Dit is het enige account"}), 400
    store.verwijder_gebruiker(user_id)
    return jsonify({"ok": True})


@app.route("/api/garmin/sync", methods=["POST"])
def api_garmin_sync():
    cfg = store.settings()
    try:
        metrics, activities = garmin_client.sync_all(
            days=int(_float(cfg.get("sync_days")) or 7),
            email=cfg.get("garmin_email") or None,
            password=cfg.get("garmin_password") or None)
    except garmin_client.GarminError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Sync mislukt: {exc}"}), 500
    dagen = sum(1 for rec in metrics if store.upsert_metric(rec, replace=True))
    acts = sum(1 for rec in activities if store.upsert_activity(rec))
    store.set_setting("last_sync", store.now())  # telt mee voor de automatische sync
    store.set_setting("last_sync_ok", store.now())  # alleen bij geslaagde poging
    try:
        health_summary.generate()  # AI-analyse bovenaan het dashboard verversen
    except Exception:
        pass  # een mislukte samenvatting mag de sync nooit laten falen
    return jsonify({"ok": True, "dagen": dagen, "activiteiten": acts,
                    "voorbeeld": metrics[0] if metrics else None})


@app.route("/api/garmin/auto-sync", methods=["POST"])
def api_garmin_auto_sync():
    """Automatische sync bij het openen van de app: maximaal één keer per half
    uur — een aanvulling op de uurlijke achtergrondsync op het hele uur. Alleen
    als Garmin ook echt is ingesteld. Elke poging (geslaagd of niet) telt als
    'laatst gesync', zodat een falende verbinding niet bij elke paginalading
    opnieuw probeert. Antwoordt met gesynced: false wanneer er niets te doen is."""
    if _recent_sync(AUTO_SYNC_MINUTEN):
        return jsonify({"ok": True, "gesynced": False, "reden": "recent-gesynced"})
    with _auto_sync_lock:
        if _recent_sync(AUTO_SYNC_MINUTEN):  # twee tabben tegelijk geopend
            return jsonify({"ok": True, "gesynced": False, "reden": "recent-gesynced"})
        res = _auto_sync_poging()
    return jsonify({"ok": True, **res})


@app.route("/api/garmin/login/start", methods=["POST"])
def api_garmin_login_start():
    """Start achtergrond-login; kan om een 2FA-code vragen (zie /login/status)."""
    data = request.get_json(force=True, silent=True) or {}
    cfg = store.settings()
    email = (data.get("garmin_email") or cfg.get("garmin_email") or "").strip()
    password = data.get("garmin_password") or cfg.get("garmin_password") or ""
    days = int(_float(cfg.get("sync_days")) or 7)
    try:
        garmin_flow.start(email, password, days)
    except garmin_client.GarminError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, **garmin_flow.status()})


@app.route("/api/garmin/login/status")
def api_garmin_login_status():
    return jsonify(garmin_flow.status())


@app.route("/api/garmin/login/mfa", methods=["POST"])
def api_garmin_login_mfa():
    data = request.get_json(force=True, silent=True) or {}
    if not garmin_flow.submit_mfa(data.get("code") or ""):
        return jsonify({"error": "Er wordt nu geen 2FA-code verwacht "
                                 "(verlopen of al verstuurd)."}), 400
    return jsonify({"ok": True})


@app.route("/api/garmin/logout", methods=["POST"])
def api_garmin_logout():
    garmin_client.clear_tokens()
    return jsonify({"ok": True, "message": "Tokens gewist — volgende login vraagt weer 2FA."})


@app.route("/api/export/metrics.csv")
def api_export_metrics():
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["datum", "stappen", "rusthartslag", "hrv", "slaap_uren",
                     "slaap_score", "gewicht_kg", "vetpercentage",
                     "actieve_kcal", "stress"])
    for m in store.get_metrics(100000):
        writer.writerow([m["date"], m["steps"], m["resting_hr"], m["hrv"],
                         m["sleep_hours"], m["sleep_score"], m["weight"],
                         m["body_fat"], m["active_calories"], m["stress"]])
    return Response(out.getvalue(), mimetype="text/csv", headers={
        "Content-Disposition": "attachment; filename=vitalytics-metingen.csv"})


@app.route("/api/export/meals.csv")
def api_export_meals():
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["tijdstip", "naam", "kcal", "eiwit_g", "koolhydraten_g",
                     "vet_g", "gezondheidsscore", "foto"])
    for m in store.get_meals(100000):
        writer.writerow([m["ts"], m["name"], m["kcal"], m["protein"], m["carbs"],
                         m["fat"], m["health_score"], m["photo_path"] or ""])
    return Response(out.getvalue(), mimetype="text/csv", headers={
        "Content-Disposition": "attachment; filename=vitalytics-maaltijden.csv"})


@app.route("/api/export/backup.json")
def api_export_backup():
    payload = {
        "geexporteerd": store.now(),
        "metingen": store.get_metrics(100000),
        "maaltijden": store.get_meals(100000),
        "advies": store.get_advice(100000),
        "profiel": {k: v for k, v in store.settings().items()
                    if k not in ("garmin_password", "ai_api_key")},
    }
    return Response(json.dumps(payload, ensure_ascii=False, indent=1),
                    mimetype="application/json", headers={
        "Content-Disposition": "attachment; filename=vitalytics-backup.json"})


@app.route("/api/ai/test", methods=["POST"])
def api_ai_test():
    """Korte proefgeneratie via de actieve backend (API of Ollama)."""
    try:
        antwoord, bron = ai_utils.generate("Antwoord met uitsluitend het woord: OK",
                                           temperature=0, timeout=60, num_predict=10)
        return jsonify({"ok": True, "bron": bron,
                        "antwoord": antwoord.strip()[:80]})
    except Exception as exc:
        return jsonify({"error": f"Test mislukt: {exc}"}), 503


@app.route("/api/garmin/csv", methods=["POST"])
def api_garmin_csv():
    files = [f for f in request.files.getlist("files") if f and f.filename]
    if not files:
        return jsonify({"error": "Geen CSV-bestanden ontvangen"}), 400
    imported = 0
    for f in files:
        text = f.read().decode("utf-8-sig", errors="replace")
        for rec in garmin_client.import_csv(text):
            if store.upsert_metric(rec):
                imported += 1
    return jsonify({"ok": True, "rijen": imported})


@app.route("/api/demo/seed", methods=["POST"])
def api_demo_seed():
    # nooit echte Garmin-rijen overschrijven met demodata
    echt = {m["date"] for m in store.get_metrics(100000) if m.get("source") == "garmin"}
    toegevoegd = 0
    for rec in garmin_client.demo_metrics(14):
        if rec["date"] in echt:
            continue
        store.upsert_metric(rec)
        toegevoegd += 1
    return jsonify({"ok": True, "metric_dagen": toegevoegd,
                    "maaltijden_toegevoegd": _seed_demo_meals(),
                    "activiteiten_toegevoegd": _seed_demo_activities()})


@app.route("/api/meals/analyze", methods=["POST"])
def api_meal_analyze():
    """AI-schatting van naam en voedingswaarden op basis van een maaltijdfoto."""
    photo = request.files.get("photo")
    if not photo or not photo.filename:
        return jsonify({"error": "Geen foto ontvangen"}), 400
    try:
        result, bron = meal_vision.analyze_photo(photo.read())
    except Exception as exc:
        return jsonify({"error": f"Foto-analyse mislukt: {exc}"}), 503
    return jsonify({"ok": True, "bron": bron, **result})


@app.route("/api/meals/estimate", methods=["POST"])
def api_meal_estimate():
    """AI-schatting van naam en voedingswaarden op basis van een omschrijving."""
    data = request.get_json(force=True, silent=True) or {}
    beschrijving = (data.get("beschrijving") or "").strip()
    if not beschrijving:
        return jsonify({"error": "Beschrijf eerst kort wat je gegeten hebt"}), 400
    try:
        result, bron = meal_vision.estimate_text(beschrijving)
    except Exception as exc:
        return jsonify({"error": f"AI-schatting mislukt: {exc}"}), 503
    return jsonify({"ok": True, "bron": bron, **result})


@app.route("/api/meals/save", methods=["POST"])
def api_meal_save():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("naam") or "").strip()
    if not name:
        return jsonify({"error": "Naam is verplicht"}), 400
    ts = _meal_ts(data.get("datum"))
    if ts is None:
        return jsonify({"error": "Kies een geldige dag (vandaag of eerder)"}), 400
    meal_id = store.save_meal(
        name=name,
        kcal=_float(data.get("kcal")), protein=_float(data.get("eiwit")),
        carbs=_float(data.get("koolhydraten")), fat=_float(data.get("vet")),
        health_score=_float(data.get("gezondheidsscore")),
        analysis=json.dumps({"onderdelen": data.get("onderdelen") or [],
                             "opmerking": data.get("opmerking") or ""},
                            ensure_ascii=False),
        analyzed=0, ts=ts)
    return jsonify({"ok": True, "id": meal_id})


@app.route("/api/meals/<int:meal_id>", methods=["GET"])
def api_meal_get(meal_id):
    m = store.get_meal(meal_id)
    if not m:
        return jsonify({"error": "Maaltijd niet gevonden"}), 404
    try:
        meta = json.loads(m.get("analysis") or "{}")
        if not isinstance(meta, dict):
            meta = {}
    except (TypeError, ValueError):
        meta = {}
    return jsonify({"id": m["id"], "naam": m["name"], "kcal": m["kcal"],
                    "eiwit": m["protein"], "koolhydraten": m["carbs"], "vet": m["fat"],
                    "gezondheidsscore": m["health_score"],
                    "opmerking": meta.get("opmerking") or "",
                    "datum": (m.get("ts") or "")[:10],
                    "photo_file": m.get("photo_path") or ""})


@app.route("/api/meals/<int:meal_id>", methods=["PUT"])
def api_meal_update(meal_id):
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("naam") or "").strip()
    if not name:
        return jsonify({"error": "Naam is verplicht"}), 400
    ts = _meal_ts(data.get("datum")) if data.get("datum") else None
    if data.get("datum") and ts is None:
        return jsonify({"error": "Kies een geldige dag (vandaag of eerder)"}), 400
    if not store.update_meal(
            meal_id, name=name,
            kcal=_float(data.get("kcal")), protein=_float(data.get("eiwit")),
            carbs=_float(data.get("koolhydraten")), fat=_float(data.get("vet")),
            health_score=_float(data.get("gezondheidsscore")),
            opmerking=data.get("opmerking"), ts=ts):
        return jsonify({"error": "Maaltijd niet gevonden"}), 404
    return jsonify({"ok": True})


@app.route("/api/meals/<int:meal_id>", methods=["DELETE"])
def api_meal_delete(meal_id):
    store.delete_meal(meal_id)
    return jsonify({"ok": True})


@app.route("/api/advice/generate", methods=["POST"])
def api_advice_generate():
    data = request.get_json(force=True, silent=True) or {}
    mode = data.get("mode")
    if mode not in (None, "ai", "rules"):
        return jsonify({"error": "Onbekende modus"}), 400
    try:
        return jsonify(advisor.generate(mode))
    except advisor.AdvisorError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Advies genereren mislukt: {exc}"}), 500


@app.route("/api/advice/<int:advice_id>", methods=["DELETE"])
def api_advice_delete(advice_id):
    """Verwijder één opgeslagen advies uit de historie."""
    store.delete_advice(advice_id)
    return jsonify({"ok": True})


@app.route("/api/reset", methods=["POST"])
def api_reset():
    store.reset_all()
    return jsonify({"ok": True})


# ---------------------------------------------------------------- helpers

def _seed_demo_activities():
    if store.get_activities(1):
        return 0
    d = store.today()
    def _ago(days, time):
        day = (datetime.strptime(d, "%Y-%m-%d") - timedelta(days=days)).strftime("%Y-%m-%d")
        return f"{day} {time}:00"
    demo = [
        {"activity_id": "demo-1", "start_time": _ago(1, "07:15"), "name": "Tempoloop 10 km",
         "type": "running", "duration_s": 2700, "distance_m": 10000, "avg_hr": 152,
         "max_hr": 171, "calories": 650, "avg_cadence": 172, "aerobic_te": 3.4,
         "anaerobic_te": 0.8, "source": "demo"},
        {"activity_id": "demo-2", "start_time": _ago(3, "18:40"), "name": "Herstelloop",
         "type": "running", "duration_s": 1930, "distance_m": 5000, "avg_hr": 122,
         "max_hr": 138, "calories": 340, "avg_cadence": 158, "aerobic_te": 1.6, "source": "demo"},
        {"activity_id": "demo-3", "start_time": _ago(5, "09:05"), "name": "Zondagse rondje",
         "type": "cycling", "duration_s": 5700, "distance_m": 38000, "avg_hr": 138,
         "max_hr": 158, "calories": 950, "elevation_m": 240, "aerobic_te": 2.7, "source": "demo"},
        {"activity_id": "demo-4", "start_time": _ago(6, "19:30"), "name": "Krachtsessie bovenlichaam",
         "type": "strength_training", "duration_s": 3000, "avg_hr": 118, "max_hr": 142,
         "calories": 320, "aerobic_te": 0.9, "anaerobic_te": 1.4, "source": "demo"},
        {"activity_id": "demo-5", "start_time": _ago(8, "08:00"), "name": "Avondduurloop",
         "type": "running", "duration_s": 3900, "distance_m": 11500, "avg_hr": 143,
         "max_hr": 156, "calories": 780, "avg_cadence": 166, "aerobic_te": 2.9, "source": "demo"},  # Avondduurloop
        {"activity_id": "demo-6", "start_time": _ago(9, "17:45"), "name": "Avondwandeling",
         "type": "walking", "duration_s": 3300, "distance_m": 4800, "avg_hr": 102,
         "calories": 240, "aerobic_te": 0.8, "source": "demo"},
    ]
    return sum(1 for rec in demo if store.upsert_activity(rec))


def _seed_demo_meals():
    if store.get_meals_today():
        return 0
    demo = [
        ("Ontbijt: havermout met banaan en pindakaas", 520, 18, 72, 16, 8),
        ("Lunch: volkoren broodje kip-kaas", 610, 34, 58, 24, 6),
        ("Snack: Griekse yoghurt met walnoten", 260, 15, 12, 17, 9),
    ]
    for name, kcal, p, c, f, score in demo:
        store.save_meal(
            name=name, kcal=kcal, protein=p, carbs=c, fat=f, health_score=score,
            analysis=json.dumps({"opmerking": "demo-invoer"}, ensure_ascii=False),
            analyzed=0)
    return len(demo)


def _avg(metrics, key, n=7):
    vals = [m[key] for m in metrics[-n:] if m.get(key) is not None]
    return round(sum(vals) / len(vals)) if vals else None


def _spark(metrics, key, n=14):
    vals = [m[key] for m in metrics if m.get(key) is not None][-n:]
    return ",".join(f"{v:g}" for v in vals)


def _latest_row(metrics, key):
    """Nieuwste meting waarin `key` een waarde heeft (iets oudere dag is beter dan leeg)."""
    for m in reversed(metrics):
        if m.get(key) is not None:
            return m
    return None


def _cards(metrics):
    if not metrics:
        return []
    ctx = advisor.compute_context()
    score, _warnings = advisor.rule_readiness(ctx)
    cards = [{"label": "Trainingsklaarheid", "value": score, "unit": "/100",
              "spark": "", "hint": "Schatting uit slaap, HRV en rusthartslag"}]

    goal = int(store.get_setting("step_goal") or 10000)

    steps_row = _latest_row(metrics, "steps")
    if steps_row:
        hint_bits = []
        pct = None
        if goal > 0:
            pct = round(steps_row["steps"] / goal * 100)
            hint_bits.append(f"{pct}% van dagdoel {goal:,}".replace(",", "."))
        avg = _avg(metrics, "steps")
        if avg:
            hint_bits.append(f"7-daags gem. {avg:,}".replace(",", "."))
        kaart = {"label": "Stappen",
                 "value": f"{steps_row['steps']:,}".replace(",", "."),
                 "unit": "stappen",
                 "hint": " · ".join(hint_bits)}
        if pct is not None:
            kaart["doel_pct"] = max(0, min(100, pct))
        cards.append(kaart)

    rhr_row = _latest_row(metrics, "resting_hr")
    if rhr_row:
        cards.append({"label": "Rusthartslag", "value": rhr_row["resting_hr"], "unit": "bpm",
                      "spark": _spark(metrics, "resting_hr"),
                      "hint": f"7-daags gem. {_avg(metrics, 'resting_hr') or '-'} bpm"})

    hrv_row = _latest_row(metrics, "hrv")
    if hrv_row:
        baseline = ctx.get("hrv_baseline")
        if baseline:
            hint = f"{(hrv_row['hrv'] - baseline) / baseline * 100:+.0f}% t.o.v. basislijn"
        else:
            hint = f"7-daags gem. {_avg(metrics, 'hrv') or '-'} ms"
        cards.append({"label": "HRV (nacht)", "value": hrv_row["hrv"], "unit": "ms",
                      "spark": _spark(metrics, "hrv"), "hint": hint})

    sleep_row = _latest_row(metrics, "sleep_hours")
    if sleep_row:
        cards.append({"label": "Slaap", "value": sleep_row["sleep_hours"], "unit": "uur",
                      "spark": _spark(metrics, "sleep_hours"),
                      "hint": f"7-daags gem. {_avg(metrics, 'sleep_hours') or '-'} uur"})

    weight_row = _latest_row(metrics, "weight")
    if weight_row:
        first = next((m["weight"] for m in metrics if m.get("weight") is not None), None)
        delta = round(weight_row["weight"] - first, 1) if first is not None else 0
        cards.append({"label": "Gewicht", "value": weight_row["weight"], "unit": "kg",
                      "spark": _spark(metrics, "weight"),
                      "hint": f"{delta:+.1f} kg sinds start van de periode".replace(".", ",") + ""})
    else:
        profile_weight = _float(store.get_setting("weight_kg"))
        if profile_weight:
            cards.append({"label": "Gewicht", "value": profile_weight, "unit": "kg",
                          "spark": "",
                          "hint": "uit je profiel — log je gewicht in Garmin (of weeg met een gekoppelde schaal) voor een trend"})
    return cards


def _lan_adressen():
    """IPv4-adressen van deze machine, voor de adresjes bij het opstarten."""
    try:
        _, ips, _ = socket.gethostbyname_ex(socket.gethostname())
        return [ip for ip in ips if not ip.startswith("127.")]
    except OSError:
        return []


if __name__ == "__main__":
    print("Vitalytics \u2014 lokale gezondheidscoach")
    if HOST in ("0.0.0.0", ""):
        print("Waarschuwing: de app is nu bereikbaar op je hele netwerk \u2014 gebruik")
        print("dit alleen op een vertrouwd thuisnetwerk en zet niets door naar internet.")
    adresjes = [f"http://{HOST}:{PORT}"]
    if HOST in ("0.0.0.0", ""):
        adresjes += [f"http://{ip}:{PORT}" for ip in _lan_adressen()]
    print("\n  " + "\n  ".join(adresjes) + "\n")
    try:
        from waitress import serve
        print("Server: waitress (productie)")
        serve(app, host=HOST, port=PORT, threads=8)
    except ImportError:
        print("Server: Flask dev-server \u2014 voor netwerkgebruik liever waitress:")
        print("  python -m pip install waitress")
        app.run(host=HOST, port=PORT, debug=False, threaded=True)