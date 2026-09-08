"""Gezondheidsdata ophalen: Garmin Connect (garminconnect), CSV-import of demodata.

Bevat ook GarminLoginFlow: een achtergrond-login met 2FA-ondersteuning.
De eerste keer log je in met een code uit je Garmin-app, sms of e-mail;
daarna hergebruikt de app de opgeslagen tokens (data/garmin-tokens)
zonder opnieuw 2FA te vragen."""
import csv
import importlib.util
import io
import os
import threading
import random
from datetime import date, datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN_DIR = os.path.join(BASE_DIR, "data", "garmin-tokens")


def garmin_available():
    return importlib.util.find_spec("garminconnect") is not None


class GarminError(Exception):
    pass


def _f(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _find_number(obj, keywords, depth=0):
    """Zoek recursief naar de eerste numerieke waarde onder een van de keys.
    Maakt de code bestand tegen API-wijzigingen in garminconnect."""
    if depth > 7 or obj is None:
        return None
    if isinstance(obj, dict):
        for k, v in obj.items():
            low = str(k).lower()
            if (any(kw in low for kw in keywords)
                    and isinstance(v, (int, float)) and not isinstance(v, bool)):
                return v
        for v in obj.values():
            found = _find_number(v, keywords, depth + 1)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_number(item, keywords, depth + 1)
            if found is not None:
                return found
    return None


# ---------------------------------------------------------- Garmin Connect

def _client(email, password, prompt_mfa=None):
    """Maak een Garmin-client; vereist garminconnect."""
    if not garmin_available():
        raise GarminError("De package 'garminconnect' is niet geinstalleerd. "
                          "Installeer met: python -m pip install garminconnect")
    from garminconnect import Garmin
    try:
        return Garmin(email=email or "", password=password or "", prompt_mfa=prompt_mfa)
    except Exception as exc:
        raise GarminError(f"Kon Garmin-client niet aanmaken: {exc}") from exc


def fetch_records(client, days=7):
    """Haal de laatste `days` dagen metingen op van een ingelogde client."""
    records = []
    for offset in range(int(days)):
        day = (date.today() - timedelta(days=offset)).isoformat()
        rec = {"date": day, "source": "garmin"}
        try:
            summary = client.get_user_summary(day) or {}
            rec["steps"] = summary.get("steps") or _find_number(summary, ["steps"])
            rec["resting_hr"] = (summary.get("restingHeartRate")
                                 or _find_number(summary, ["restingheartrate"]))
            rec["active_calories"] = (summary.get("activeCalories")
                                      or _find_number(summary, ["activecalories"]))
        except Exception:
            pass
        try:
            sleep = client.get_sleep_data(day) or {}
            seconds = (_find_number(sleep, ["sleepTimeseconds", "sleeptimeseconds"])
                       or _find_number(sleep, ["totalsleeptime", "sleeptime"]))
            if seconds:
                hours = seconds / 3600.0 if seconds > 24 else seconds
                rec["sleep_hours"] = round(hours, 2)
        except Exception:
            pass
        try:
            hrv = client.get_hrv_data(day) or {}
            value = _find_number(hrv, ["lastnightaverage", "lastnightavg", "hrvvalue"])
            if value:
                rec["hrv"] = round(float(value), 1)
        except Exception:
            pass
        try:
            body = client.get_body_composition(day) or {}
            weight = _find_number(body, ["weight"])
            if weight:
                rec["weight"] = round(weight / 1000.0, 2) if weight > 300 else round(weight, 2)
            fat = _find_number(body, ["bodyfat", "percentbodyfat", "bodyfatpct"])
            if fat:
                rec["body_fat"] = round(float(fat), 1)
        except Exception:
            pass
        if len(rec) > 2:
            records.append(rec)
    return records


def _login_client(email, password, tokenstore=TOKEN_DIR):
    """Login met token-hergebruik; MFA-accounts wijzen naar de 2FA-flow."""
    if not (email or "").strip() or not (password or "").strip():
        raise GarminError("Vul eerst je Garmin-e-mailadres en wachtwoord in "
                          "(Instellingen → Garmin Connect) en gebruik 'Verbinden met 2FA'.")

    def _mfa_blocked(*_):
        raise GarminError("Dit account gebruikt 2FA — gebruik 'Verbinden met 2FA' "
                          "in Instellingen. Daarna werkt syncen automatisch zonder 2FA.")

    client = _client(email, password, prompt_mfa=_mfa_blocked)
    try:
        client.login(tokenstore)
    except GarminError:
        raise
    except Exception as exc:
        raise GarminError(f"Login bij Garmin Connect mislukt: {exc}") from exc
    return client


def sync_all(days=7, email=None, password=None, tokenstore=TOKEN_DIR):
    """Sync metingen én activiteiten; hergebruikt opgeslagen tokens indien aanwezig."""
    client = _login_client(email, password, tokenstore)
    return fetch_records(client, days), fetch_activities(client, days)


def fetch_activities(client, days=7):
    """Haal activiteiten van de laatste `days` dagen op (tolerant geparseerd)."""
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=int(days))).isoformat()
    raw = client.get_activities_by_date(start, end) or []
    records = []
    for item in raw:
        try:
            rec = _activity_record(item)
            if rec:
                records.append(rec)
        except Exception:
            continue
    return records


def _activity_record(item):
    aid = item.get("activityId") or item.get("id")
    if not aid:
        return None
    atype = item.get("activityType")
    type_key = (atype.get("typeKey") if isinstance(atype, dict) else atype) or ""
    return {
        "activity_id": str(aid),
        "start_time": item.get("startTimeLocal") or item.get("startTimeGMT") or "",
        "name": (item.get("activityName") or "Activiteit")[:120],
        "type": type_key[:40] or "unknown",
        "duration_s": _f(item.get("duration") or item.get("elapsedDuration")),
        "distance_m": _f(item.get("distance")),
        "avg_hr": _f(item.get("averageHR")),
        "max_hr": _f(item.get("maxHR")),
        "calories": _f(item.get("calories")),
        "elevation_m": _f(item.get("elevationGain")),
        "avg_cadence": _f(item.get("averageRunningCadenceInStepsPerMinute")),
        "aerobic_te": _f(item.get("aerobicTrainingEffect")),
        "anaerobic_te": _f(item.get("anaerobicTrainingEffect")),
        "source": "garmin",
    }


# ------------------------------------------------- achtergrond-login met 2FA

class GarminLoginFlow:
    """Login in een achtergrondthread; de 2FA-code komt via de webapp binnen.

    Status: idle -> in_progress -> (mfa_required -> in_progress) -> ok | error
    Na een geslaagde login worden de tokens bewaard, zodat daarna gesynct
    kan worden zonder 2FA."""

    MFA_TIMEOUT = 300  # seconden

    def __init__(self, on_sync):
        self._on_sync = on_sync
        self._lock = threading.Lock()
        self._thread = None
        self._status = "idle"
        self._message = ""
        self._days = 7
        self._email = ""
        self._password = ""
        self._mfa_event = threading.Event()
        self._mfa_code = None

    def start(self, email, password, days=7):
        with self._lock:
            if self._status == "in_progress":
                raise GarminError("Er loopt al een login — wacht tot deze klaar is.")
            if not (email or "").strip() or not (password or "").strip():
                raise GarminError("Vul eerst je Garmin-e-mailadres en wachtwoord in.")
            self._email, self._password = email.strip(), password
            self._days = int(days or 7)
            self._status = "in_progress"
            self._message = "Verbinding maken met Garmin…"
            self._mfa_event.clear()
            self._mfa_code = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def submit_mfa(self, code):
        with self._lock:
            if self._status != "mfa_required":
                return False
            self._mfa_code = (code or "").strip()
            self._mfa_event.set()
            self._status = "in_progress"
            self._message = "Code gecontroleerd bij Garmin…"
            return True

    def status(self):
        with self._lock:
            return {"status": self._status, "message": self._message}

    def _set(self, status, message):
        with self._lock:
            self._status, self._message = status, message

    def _run(self):
        def ask_mfa():
            self._set("mfa_required",
                      "Voer de 2FA-code uit je Garmin-app, sms of e-mail in.")
            self._mfa_event.wait(timeout=self.MFA_TIMEOUT)
            with self._lock:
                code, self._mfa_code = self._mfa_code, None
                self._mfa_event.clear()
            if not code:
                raise GarminError("Geen 2FA-code ontvangen "
                                  f"(time-out na {self.MFA_TIMEOUT} seconden).")
            return code

        try:
            client = _client(self._email, self._password, prompt_mfa=ask_mfa)
            client.login(TOKEN_DIR)  # laadt tokens, of logt in en slaat ze op
            metrics = fetch_records(client, self._days)
            try:
                activities = fetch_activities(client, self._days)
            except Exception:
                activities = []
            dagen, acts = self._on_sync(metrics, activities)
            extra = "" if acts else " (activiteiten: niets nieuws of ophaalfout)"
            self._set("ok", f"Ingelogd en gesynct: {dagen} dag(en) + {acts} activiteit(en){extra}.")
        except GarminError as exc:
            self._set("error", str(exc))
        except Exception as exc:
            self._set("error", f"Login bij Garmin mislukt: {exc}")


def clear_tokens():
    """Verwijder opgeslagen Garmin-tokens; volgende login vraagt weer 2FA."""
    import shutil
    shutil.rmtree(TOKEN_DIR, ignore_errors=True)
    return True


# ---------------------------------------------------------- CSV-import

def import_csv(text):
    """Tolerante import van Garmin-export-CSV's (stappen, slaap, gewicht, HRV, ...)."""
    records = []
    for raw in csv.DictReader(io.StringIO(text)):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items() if k}
        date_raw = next((row[k] for k in row if "date" in k and row[k]), None)
        if not date_raw:
            continue
        rec = {"date": _norm_date(date_raw), "source": "csv"}
        steps = _cell(row, ("steps",))
        if steps is not None:
            rec["steps"] = int(steps)
        rhr = _cell(row, ("resting heart", "restingheart", "resting hr", "rhr"))
        if rhr is not None:
            rec["resting_hr"] = round(rhr, 1)
        sleep = _cell(row, ("total sleep", "sleeptime", "sleep time", "asleep"))
        if sleep is not None:
            rec["sleep_hours"] = round(sleep / 3600.0 if sleep > 24 else sleep, 2)
        weight = _cell(row, ("weight",))
        if weight is not None:
            rec["weight"] = round(weight / 1000.0, 2) if weight > 300 else round(weight, 2)
        hrv = _cell(row, ("hrv",))
        if hrv is not None:
            rec["hrv"] = round(hrv, 1)
        calories = _cell(row, ("active calories", "activecalories"))
        if calories is not None:
            rec["active_calories"] = int(calories)
        fat = _cell(row, ("body fat", "bodyfat"))
        if fat is not None:
            rec["body_fat"] = round(fat, 1)
        if len(rec) > 2:
            records.append(rec)
    return records


def _cell(row, keywords):
    for key, value in row.items():
        if any(kw in key for kw in keywords):
            try:
                return float(str(value).replace(",", "."))
            except ValueError:
                continue
    return None


def _norm_date(value):
    value = str(value).strip().replace(".", "-")
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m-%d-%Y", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return value[:10]


# ---------------------------------------------------------- demodata

def demo_metrics(days=14):
    """Realistische demodata zodat de app direct iets te laten zien heeft."""
    rnd = random.Random(20260905)
    records = []
    weight = 82.6
    for offset in range(int(days) - 1, -1, -1):
        day = (date.today() - timedelta(days=offset)).isoformat()
        weight = max(78.0, weight - 0.07 + rnd.uniform(-0.15, 0.12))
        sleep = round(rnd.uniform(5.4, 8.6), 1)
        steps = rnd.randint(4200, 15800)
        hrv = min(72, max(30, 44 + (sleep - 7) * 6 + rnd.uniform(-6, 6)))
        rhr = min(66, max(48, 58 - (steps - 9000) / 1200 + rnd.uniform(-1.5, 1.5)))
        records.append({
            "date": day, "source": "demo", "steps": steps,
            "resting_hr": round(rhr), "hrv": round(hrv, 1), "sleep_hours": sleep,
            "sleep_score": int(min(95, max(40, sleep * 11 + rnd.uniform(-8, 8)))),
            "weight": round(weight, 1),
            "body_fat": round(21.5 - (82.6 - weight) * 0.9, 1),
            "active_calories": int(steps * 0.045),
            "stress": round(rnd.uniform(15, 55)),
        })
    return records