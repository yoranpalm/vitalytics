"""SQLite-opslag voor Vitalytics. Alles staat lokaal in de map data/."""
import json
import os
import sqlite3
import threading
from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash

# versleuteling-at-rest: zonder de package cryptography wordt er niet
# versleuteld en blijft de app gewoon werken (alleen onveiliger)
try:
    from cryptography.fernet import Fernet, InvalidToken
    _FERNET_KLAAR = True
except ImportError:
    _FERNET_KLAAR = False

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
DB_PATH = os.path.join(DATA_DIR, "coach.db")
os.makedirs(UPLOAD_DIR, exist_ok=True)

_LOCK = threading.Lock()
_METRIC_FIELDS = ("steps", "resting_hr", "hrv", "sleep_hours", "sleep_score",
                  "weight", "body_fat", "active_calories", "stress", "source")

# ------------------------------------------------------ versleuteling-at-rest
# Garmin-wachtwoord en AI-API-sleutel staan versleuteld (Fernet) in de
# database; de sleutel staat in data/crypto-key. Lekt er alleen de database
# (bijv. een backup), dan lekken deze geheimen niet mee. De instellingen-
# pagina en de sync lezen ze transparant uit.
_ENC_VOORVOEGSEL = "enc:v1:"
_ENC_SLEUTELS = ("garmin_password", "ai_api_key")
_CRYPTO_PAD = os.path.join(DATA_DIR, "crypto-key")


def _crypto_sleutel():
    """Fernet-sleutel uit data/crypto-key; eenmalig aangemaakt."""
    try:
        with open(_CRYPTO_PAD) as f:
            waarde = f.read().strip()
        if waarde:
            return waarde
    except OSError:
        pass
    waarde = Fernet.generate_key().decode()
    with open(_CRYPTO_PAD, "w") as f:
        f.write(waarde)
    try:
        os.chmod(_CRYPTO_PAD, 0o600)
    except OSError:
        pass
    return waarde


def _fernet():
    return Fernet(_crypto_sleutel().encode())


def _versleutel(waarde):
    if not _FERNET_KLAAR or waarde in ("", None):
        return waarde
    return _ENC_VOORVOEGSEL + _fernet().encrypt(str(waarde).encode()).decode()


def _ontsleutel(waarde):
    """Versleutelde waarde teruggeven als leesbare tekst; waarden zonder het
    versleutelde voorvoegsel (oude situatie) gaan ongemoeid voorbij."""
    if (not _FERNET_KLAAR or not isinstance(waarde, str)
            or not waarde.startswith(_ENC_VOORVOEGSEL)):
        return waarde
    try:
        return _fernet().decrypt(waarde[len(_ENC_VOORVOEGSEL):].encode()).decode()
    except (InvalidToken, ValueError):
        return waarde


def migratie_geheimen():
    """Bestaande leesbare geheimen in de database eenmalig versleuteld weg
    schrijven (oude installaties vóór deze maatregel)."""
    if not _FERNET_KLAAR:
        return
    with _connect() as conn:
        for sleutel in _ENC_SLEUTELS:
            row = conn.execute("SELECT value FROM profile WHERE key = ?",
                               (sleutel,)).fetchone()
            if not row:
                continue
            try:
                waarde = json.loads(row["value"])
            except (TypeError, ValueError):
                waarde = row["value"]
            if (isinstance(waarde, str) and waarde
                    and not waarde.startswith(_ENC_VOORVOEGSEL)):
                conn.execute("UPDATE profile SET value = ? WHERE key = ?",
                             (json.dumps(_versleutel(waarde)), sleutel))


def today():
    return datetime.now().strftime("%Y-%m-%d")


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _LOCK, _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS profile (
                key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS metrics (
                date TEXT PRIMARY KEY, steps INTEGER, resting_hr REAL, hrv REAL,
                sleep_hours REAL, sleep_score INTEGER, weight REAL, body_fat REAL,
                active_calories INTEGER, stress REAL, source TEXT);
            CREATE TABLE IF NOT EXISTS meals (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL,
                photo_path TEXT, name TEXT NOT NULL, kcal REAL, protein REAL,
                carbs REAL, fat REAL, health_score REAL, analysis TEXT,
                analyzed INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS advice (
                id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
                readiness REAL, payload TEXT, source TEXT);
            CREATE TABLE IF NOT EXISTS activities (
                activity_id TEXT PRIMARY KEY, start_time TEXT, name TEXT,
                type TEXT, duration_s REAL, distance_m REAL, avg_hr REAL,
                max_hr REAL, calories REAL, elevation_m REAL, avg_cadence REAL,
                aerobic_te REAL, anaerobic_te REAL, training_load REAL,
                max_cadence REAL, source TEXT);
            CREATE TABLE IF NOT EXISTS training_plan (
                id INTEGER PRIMARY KEY AUTOINCREMENT, week TEXT NOT NULL,
                weekday INTEGER NOT NULL, sport TEXT NOT NULL,
                minutes INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS training_goals (
                week TEXT PRIMARY KEY, sessions INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS training_tips (
                week TEXT PRIMARY KEY, created_at TEXT NOT NULL,
                payload TEXT NOT NULL, source TEXT);
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                pin_hash TEXT, pin_len INTEGER,
                created_at TEXT);
        """)

        # --- migratie: weekdoelen en schema's koppelen aan een account ---
        # Bestaande installaties hadden deze tabellen apparaat-breed; de rijen
        # gaan naar de eerste echte gebruiker (demo telt niet mee). Daarna is
        # (week, gebruiker) de sleutel.
        echte = conn.execute("SELECT username FROM users WHERE username != 'demo' "
                             "ORDER BY id LIMIT 1").fetchone()
        eigenaar = echte["username"] if echte else None
        for tabel in ("training_plan", "training_goals", "training_tips"):
            kolommen = [r["name"] for r in conn.execute(f"PRAGMA table_info({tabel})")]
            if "gebruiker" not in kolommen:
                conn.execute(f"ALTER TABLE {tabel} ADD COLUMN gebruiker TEXT NOT NULL DEFAULT ''")
        if eigenaar:
            for tabel in ("training_plan", "training_goals", "training_tips"):
                conn.execute(f"UPDATE {tabel} SET gebruiker = ? WHERE gebruiker = ''",
                             (eigenaar,))
        # training_goals en training_tips hadden week als unieke sleutel; per
        # account moet (week, gebruiker) uniek zijn — tabellen eenmalig herbouwen
        for tabel in ("training_goals", "training_tips"):
            info = list(conn.execute(f"PRAGMA table_info({tabel})"))
            pk = {r["name"] for r in info if r["pk"]}
            if pk == {"week", "gebruiker"}:
                continue
            structuur = {
                "training_goals": "week TEXT NOT NULL, gebruiker TEXT NOT NULL DEFAULT '', sessions INTEGER NOT NULL",
                "training_tips": ("week TEXT NOT NULL, gebruiker TEXT NOT NULL DEFAULT '', "
                                  "created_at TEXT NOT NULL, payload TEXT NOT NULL, source TEXT"),
            }[tabel]
            kopie = ", ".join(r["name"] for r in info)
            conn.execute(f"CREATE TABLE {tabel}_nieuw ({structuur}, PRIMARY KEY (week, gebruiker))")
            conn.execute(f"INSERT OR IGNORE INTO {tabel}_nieuw SELECT {kopie} FROM {tabel}")
            conn.execute(f"DROP TABLE {tabel}")
            conn.execute(f"ALTER TABLE {tabel}_nieuw RENAME TO {tabel}")

        # --- migratie: extra Garmin-velden per activiteit (belasting, piek-cadans) ---
        activiteit_kolommen = [r["name"] for r in conn.execute("PRAGMA table_info(activities)")]
        for kolom in ("training_load", "max_cadence"):
            if kolom not in activiteit_kolommen:
                conn.execute(f"ALTER TABLE activities ADD COLUMN {kolom} REAL")

        # --- migratie: pincode-login per account (lockscreen op /login) ---
        gebruiker_kolommen = [r["name"] for r in conn.execute("PRAGMA table_info(users)")]
        if "pin_hash" not in gebruiker_kolommen:
            conn.execute("ALTER TABLE users ADD COLUMN pin_hash TEXT")
        if "pin_len" not in gebruiker_kolommen:
            conn.execute("ALTER TABLE users ADD COLUMN pin_len INTEGER")


# ------------------------------------------------------------- instellingen

_DEFAULTS = {"age": "", "sex": "", "height_cm": "", "weight_kg": "",
             "goal": "presteren", "step_goal": 10000, "sync_days": 7,
             "garmin_email": "", "garmin_password": "", "model_advice": "auto",
             "ai_provider": "ollama", "ai_api_key": "", "ai_base_url": "",
             "ai_model": ""}


def set_setting(key, value):
    if key in _ENC_SLEUTELS:
        value = _versleutel(value)  # gevoelige instellingen nooit leesbaar op schijf
    with _LOCK, _connect() as conn:
        conn.execute(
            "INSERT INTO profile (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)))


def get_setting(key, default=None):
    with _connect() as conn:
        row = conn.execute("SELECT value FROM profile WHERE key = ?", (key,)).fetchone()
    if row is None:
        return _DEFAULTS.get(key, default) if key in _DEFAULTS else default
    try:
        waarde = json.loads(row["value"])
    except (TypeError, ValueError):
        waarde = row["value"]
    if key in _ENC_SLEUTELS:
        return _ontsleutel(waarde)
    return waarde


def settings():
    out = dict(_DEFAULTS)
    with _connect() as conn:
        for row in conn.execute("SELECT key, value FROM profile"):
            try:
                waarde = json.loads(row["value"])
            except (TypeError, ValueError):
                waarde = row["value"]
            if row["key"] in _ENC_SLEUTELS:
                waarde = _ontsleutel(waarde)
            out[row["key"]] = waarde
    return out


# ------------------------------------------------------------- metingen

def upsert_metric(rec, replace=False):
    """Schrijf dagmetingen. replace=True (Garmin-sync) vervangt de rij volledig,
    zodat oude velden (bv. demogewicht) niet kunnen blijven staan."""
    day = rec.get("date")
    clean = {k: rec[k] for k in _METRIC_FIELDS if rec.get(k) not in (None, "")}
    if not day or not clean:
        return False
    cols = ", ".join(clean)
    placeholders = ", ".join("?" * len(clean))
    updates = ", ".join(f"{k} = excluded.{k}" for k in clean)
    with _LOCK, _connect() as conn:
        if replace:
            conn.execute("DELETE FROM metrics WHERE date = ?", (day,))
        conn.execute(
            f"INSERT INTO metrics (date, {cols}) VALUES (?, {placeholders}) "
            f"ON CONFLICT(date) DO UPDATE SET {updates}",
            [day, *clean.values()])
    return True


def get_metrics(days=30):
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM metrics ORDER BY date DESC LIMIT ?", (days,)).fetchall()
    return [dict(r) for r in reversed(rows)]


# ------------------------------------------------------------- activiteiten

_ACTIVITY_FIELDS = ("start_time", "name", "type", "duration_s", "distance_m",
                    "avg_hr", "max_hr", "calories", "elevation_m", "avg_cadence",
                    "aerobic_te", "anaerobic_te", "training_load", "max_cadence",
                    "source")


def upsert_activity(rec):
    aid = str(rec.get("activity_id") or "")
    if not aid:
        return False
    clean = {k: rec[k] for k in _ACTIVITY_FIELDS if rec.get(k) is not None}
    if not clean:
        return False
    cols = ", ".join(clean)
    placeholders = ", ".join("?" * len(clean))
    updates = ", ".join(f"{k} = excluded.{k}" for k in clean)
    with _LOCK, _connect() as conn:
        conn.execute(
            f"INSERT INTO activities (activity_id, {cols}) VALUES (?, {placeholders}) "
            f"ON CONFLICT(activity_id) DO UPDATE SET {updates}",
            [aid, *clean.values()])
    return True


def get_activities(limit=200):
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM activities ORDER BY start_time DESC LIMIT ?",
            (limit,)).fetchall()
    return [dict(r) for r in rows]


# ------------------------------------------------------------- maaltijden

def save_meal(name, kcal=None, protein=None, carbs=None, fat=None,
              health_score=None, photo_file=None, analysis=None, analyzed=0,
              ts=None):
    """ts: optioneel tijdstip 'jjjj-mm-dd uu:mm' (maaltijd op een eerdere dag
    kunnen loggen); None = nu."""
    with _LOCK, _connect() as conn:
        cur = conn.execute(
            "INSERT INTO meals (ts, photo_path, name, kcal, protein, carbs, fat, "
            "health_score, analysis, analyzed) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ts or now(), photo_file, name, kcal, protein, carbs, fat,
             health_score, analysis, analyzed))
        return cur.lastrowid


def get_meals(limit=100):
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM meals ORDER BY ts DESC, id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def get_meals_today():
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM meals WHERE substr(ts, 1, 10) = ? ORDER BY id",
            (today(),)).fetchall()
    return [dict(r) for r in rows]


def get_meal(meal_id):
    with _connect() as conn:
        row = conn.execute("SELECT * FROM meals WHERE id = ?", (meal_id,)).fetchone()
    return dict(row) if row else None


def update_meal(meal_id, name, kcal=None, protein=None, carbs=None, fat=None,
                health_score=None, opmerking=None, ts=None):
    """Werk een bestaande maaltijd bij (dag, titel, macro's, score, opmerking).
    ts=None laat de oorspronkelijke dag staan."""
    with _LOCK, _connect() as conn:
        row = conn.execute("SELECT analysis FROM meals WHERE id = ?", (meal_id,)).fetchone()
        if row is None:
            return False
        try:
            meta = json.loads(row["analysis"] or "{}")
            if not isinstance(meta, dict):
                meta = {}
        except (TypeError, ValueError):
            meta = {}
        if opmerking is not None:
            meta["opmerking"] = opmerking
        cur = conn.execute(
            f"UPDATE meals SET {'ts = ?, ' if ts else ''}name = ?, kcal = ?, "
            "protein = ?, carbs = ?, fat = ?, health_score = ?, analysis = ? "
            "WHERE id = ?",
            ([ts] if ts else []) +
            [name, kcal, protein, carbs, fat, health_score,
             json.dumps(meta, ensure_ascii=False), meal_id])
        return cur.rowcount > 0


def delete_meal(meal_id):
    with _LOCK, _connect() as conn:
        conn.execute("DELETE FROM meals WHERE id = ?", (meal_id,))


# ------------------------------------------------------------- gebruikers

def gebruikers():
    """Alle accounts (zonder wachtwoord-hashes); pin_gezet voor het instellingen-UI."""
    with _connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT id, username, created_at, "
            "(pin_hash IS NOT NULL) AS pin_gezet FROM users ORDER BY username")]


def aantal_gebruikers():
    with _connect() as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]


def heeft_gebruiker(username):
    """Bestaat dit account? (voor de demo-check bij het starten)"""
    with _connect() as conn:
        return conn.execute("SELECT 1 FROM users WHERE username = ?",
                            ((username or "").strip(),)).fetchone() is not None


def maak_gebruiker(username, wachtwoord):
    """Account aanmaken; bestaat de naam al, dan wordt het wachtwoord vernieuwd."""
    h = generate_password_hash(wachtwoord)
    with _LOCK, _connect() as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT(username) DO UPDATE SET password_hash = excluded.password_hash",
            (username, h, now()))


def controleer_login(username, wachtwoord):
    """Account checken; geeft het account terug of None."""
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?",
                           ((username or "").strip(),)).fetchone()
    if row and check_password_hash(row["password_hash"], wachtwoord or ""):
        return dict(row)
    return None


def verwijder_gebruiker(user_id):
    with _LOCK, _connect() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


def zet_pin(user_id, pin):
    """Pincode (4-8 cijfers) instellen voor een account, of wissen (pin=None/'').
    Wordt gehasht bewaard, zoals het wachtwoord; pin_len onthoudt de lengte
    zodat het cijferblok op het inlogscherm automatisch kan verzenden."""
    h = generate_password_hash(str(pin)) if pin else None
    with _LOCK, _connect() as conn:
        conn.execute("UPDATE users SET pin_hash = ?, pin_len = ? WHERE id = ?",
                     (h, len(str(pin)) if pin else None, user_id))


def gebruiker_via_pin(pin):
    """Account waarvan de pincode klopt (demo uitgezonderd: read-only), of None."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM users WHERE pin_hash IS NOT NULL AND username != 'demo' "
            "ORDER BY id").fetchall()
    for row in rows:
        if check_password_hash(row["pin_hash"], str(pin)):
            return dict(row)
    return None


def pin_login_info():
    """Voor het inlogscherm: naam en lengte van de eerste ingestelde pincode
    (demo uitgezonderd), of None als er geen is."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT username, pin_len FROM users WHERE pin_hash IS NOT NULL "
            "AND username != 'demo' ORDER BY id LIMIT 1").fetchone()
    return dict(row) if row else None


# ------------------------------------------------------- trainingsschema

def get_training_plan(week, gebruiker=""):
    """Schema voor een week: {'week', 'sessions_goal', 'entries': {weekday: {...}}}."""
    with _connect() as conn:
        goal = conn.execute("SELECT sessions FROM training_goals WHERE week = ? AND gebruiker = ?",
                            (week, gebruiker)).fetchone()
        rows = conn.execute(
            "SELECT weekday, sport, minutes FROM training_plan "
            "WHERE week = ? AND gebruiker = ? ORDER BY weekday", (week, gebruiker)).fetchall()
    return {"week": week,
            "sessions_goal": goal["sessions"] if goal else None,
            "entries": {r["weekday"]: {"sport": r["sport"], "minutes": r["minutes"]}
                        for r in rows}}


def save_training_plan(week, sessions_goal, entries, gebruiker=""):
    """Vervang het schema van een week volledig voor dit account. Ongeldige regels
    worden gedempt overgeslagen (geen sport, geen minuten of onbekende dag)."""
    with _LOCK, _connect() as conn:
        if sessions_goal is None:
            conn.execute("DELETE FROM training_goals WHERE week = ? AND gebruiker = ?",
                         (week, gebruiker))
        else:
            conn.execute(
                "INSERT INTO training_goals (week, gebruiker, sessions) VALUES (?, ?, ?) "
                "ON CONFLICT(week, gebruiker) DO UPDATE SET sessions = excluded.sessions",
                (week, gebruiker, int(sessions_goal)))
        conn.execute("DELETE FROM training_plan WHERE week = ? AND gebruiker = ?",
                     (week, gebruiker))
        saved = 0
        for entry in entries:
            try:
                weekday = int(entry.get("weekday") or 0)
                minutes = int(entry.get("minutes") or 0)
            except (TypeError, ValueError):
                continue
            sport = str(entry.get("sport") or "").strip()[:60]
            if not sport or not 1 <= weekday <= 7 or minutes <= 0 or minutes > 600:
                continue
            conn.execute(
                "INSERT INTO training_plan (week, gebruiker, weekday, sport, minutes) "
                "VALUES (?, ?, ?, ?, ?)", (week, gebruiker, weekday, sport, minutes))
            saved += 1
    return saved


def get_training_tips(week, gebruiker=""):
    """Opgeslagen AI-advies bij het weekschema (of None)."""
    with _connect() as conn:
        row = conn.execute("SELECT * FROM training_tips WHERE week = ? AND gebruiker = ?",
                           (week, gebruiker)).fetchone()
    if not row:
        return None
    try:
        payload = json.loads(row["payload"] or "{}")
    except (TypeError, ValueError):
        payload = {}
    return {"created_at": row["created_at"], "source": row["source"],
            "payload": payload if isinstance(payload, dict) else {}}


def save_training_tips(week, payload, source, gebruiker=""):
    with _LOCK, _connect() as conn:
        conn.execute(
            "INSERT INTO training_tips (week, gebruiker, created_at, payload, source) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(week, gebruiker) DO UPDATE SET created_at = excluded.created_at, "
            "payload = excluded.payload, source = excluded.source",
            (week, gebruiker, now(), json.dumps(payload, ensure_ascii=False), source))


# ------------------------------------------------------------- advies

def save_advice(readiness, payload, source):
    with _LOCK, _connect() as conn:
        cur = conn.execute(
            "INSERT INTO advice (created_at, readiness, payload, source) VALUES (?, ?, ?, ?)",
            (now(), readiness, json.dumps(payload, ensure_ascii=False), source))
        return cur.lastrowid


def get_advice(limit=20):
    items = []
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM advice ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    for row in rows:
        item = dict(row)
        try:
            item["payload"] = json.loads(item.get("payload") or "{}")
        except (TypeError, ValueError):
            item["payload"] = {}
        items.append(item)
    return items


def latest_advice():
    items = get_advice(1)
    return items[0] if items else None


def delete_advice(advice_id):
    """Verwijder één advies uit de historie."""
    with _LOCK, _connect() as conn:
        conn.execute("DELETE FROM advice WHERE id = ?", (advice_id,))


# ------------------------------------------------------------- beheer

def reset_all():
    with _LOCK, _connect() as conn:
        for table in ("metrics", "meals", "advice", "activities", "profile",
                      "training_plan", "training_goals", "training_tips"):
            conn.execute(f"DELETE FROM {table}")