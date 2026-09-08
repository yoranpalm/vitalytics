"""SQLite-opslag voor Vitalytics. Alles staat lokaal in de map data/."""
import json
import os
import sqlite3
import threading
from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
DB_PATH = os.path.join(DATA_DIR, "coach.db")
os.makedirs(UPLOAD_DIR, exist_ok=True)

_LOCK = threading.Lock()
_METRIC_FIELDS = ("steps", "resting_hr", "hrv", "sleep_hours", "sleep_score",
                  "weight", "body_fat", "active_calories", "stress", "source")


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
                aerobic_te REAL, anaerobic_te REAL, source TEXT);
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
                created_at TEXT);
        """)


# ------------------------------------------------------------- instellingen

_DEFAULTS = {"age": "", "sex": "", "height_cm": "", "weight_kg": "",
             "goal": "presteren", "step_goal": 10000, "sync_days": 7,
             "garmin_email": "", "garmin_password": "", "model_advice": "auto",
             "ai_provider": "ollama", "ai_api_key": "", "ai_base_url": "",
             "ai_model": ""}


def set_setting(key, value):
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
        return json.loads(row["value"])
    except (TypeError, ValueError):
        return row["value"]


def settings():
    out = dict(_DEFAULTS)
    with _connect() as conn:
        for row in conn.execute("SELECT key, value FROM profile"):
            try:
                out[row["key"]] = json.loads(row["value"])
            except (TypeError, ValueError):
                out[row["key"]] = row["value"]
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
                    "aerobic_te", "anaerobic_te", "source")


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
    """Alle accounts (zonder wachtwoord-hashes)."""
    with _connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT id, username, created_at FROM users ORDER BY username")]


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


# ------------------------------------------------------- trainingsschema

def get_training_plan(week):
    """Schema voor een week: {'week', 'sessions_goal', 'entries': {weekday: {...}}}."""
    with _connect() as conn:
        goal = conn.execute("SELECT sessions FROM training_goals WHERE week = ?",
                            (week,)).fetchone()
        rows = conn.execute(
            "SELECT weekday, sport, minutes FROM training_plan "
            "WHERE week = ? ORDER BY weekday", (week,)).fetchall()
    return {"week": week,
            "sessions_goal": goal["sessions"] if goal else None,
            "entries": {r["weekday"]: {"sport": r["sport"], "minutes": r["minutes"]}
                        for r in rows}}


def save_training_plan(week, sessions_goal, entries):
    """Vervang het schema van een week volledig. Ongeldige regels worden gedempt
    overgeslagen (geen sport, geen minuten of onbekende dag)."""
    with _LOCK, _connect() as conn:
        if sessions_goal is None:
            conn.execute("DELETE FROM training_goals WHERE week = ?", (week,))
        else:
            conn.execute(
                "INSERT INTO training_goals (week, sessions) VALUES (?, ?) "
                "ON CONFLICT(week) DO UPDATE SET sessions = excluded.sessions",
                (week, int(sessions_goal)))
        conn.execute("DELETE FROM training_plan WHERE week = ?", (week,))
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
                "INSERT INTO training_plan (week, weekday, sport, minutes) "
                "VALUES (?, ?, ?, ?)", (week, weekday, sport, minutes))
            saved += 1
    return saved


def get_training_tips(week):
    """Opgeslagen AI-advies bij het weekschema (of None)."""
    with _connect() as conn:
        row = conn.execute("SELECT * FROM training_tips WHERE week = ?",
                           (week,)).fetchone()
    if not row:
        return None
    try:
        payload = json.loads(row["payload"] or "{}")
    except (TypeError, ValueError):
        payload = {}
    return {"created_at": row["created_at"], "source": row["source"],
            "payload": payload if isinstance(payload, dict) else {}}


def save_training_tips(week, payload, source):
    with _LOCK, _connect() as conn:
        conn.execute(
            "INSERT INTO training_tips (week, created_at, payload, source) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(week) DO UPDATE SET created_at = excluded.created_at, "
            "payload = excluded.payload, source = excluded.source",
            (week, now(), json.dumps(payload, ensure_ascii=False), source))


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