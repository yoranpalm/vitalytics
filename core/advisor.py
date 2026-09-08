"""Gepersonaliseerd advies: AI via lokale Ollama-modellen, met een
regelgebaseerde engine als valbacup zodat de app altijd werkt.

De AI krijgt alle data (metingen, maaltijden, activiteiten, profiel) plus de
regelengine-berekening als referentie en levert een onderbouwd advies in JSON.
De regelengine rekent dezelfde cijfers deterministisch uit (HRV-trend, slaap,
rust-HF, Mifflin-St Jeor) en dient als fallback en als feitenkader voor de AI."""
import json
import statistics
from datetime import datetime

from . import ai_utils, store


class AdvisorError(Exception):
    """Gerezen wanneer een expliciet gevraagde AI-generatie niet lukt."""

SYSTEM = (
    "Je bent een ervaren trainingswetenschapper en geregistreerd di\u00ebtist. "
    "Antwoord altijd in het Nederlands en uitsluitend met geldige JSON. "
    "Schrijf in heldere, alledaagse taal die iemand zonder sportwetenschappelijke "
    "achtergrond meteen begrijpt: leg vaktermen (zoals HRV, zone 2, supercompensatie) "
    "altijd eerst in gewone woorden uit. "
    "Onderbouw advies met fysiologische mechanismen en gevestigde richtlijnen "
    "(zoals HRV als marker van parasympathisch herstel, supercompensatie, "
    "eiwitinname van 1,6-2,2 g/kg/dag volgens internationale sportvoedingsrichtlijnen, "
    "Mifflin-St Jeor voor rustmetabolisme). Verzin GEEN specifieke studies, auteurs, "
    "jaren of DOIs. Wees eerlijk over onzekerheid en individuele variatie. "
    "Geen losse steekwoorden maar volledige, uitgebreide uitleg in begrijpelijke taal. "
    "Je advies is educatief en geen medisch advies.")


def _f(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def rel_dag(datum, vandaag_date=None):
    """Anonieme dagnotatie voor cloud-prompts: 'vandaag', 'gisteren', '-3 dagen'.
   Absolute data zijn op zichzelf quasi-identificeerbaar (startdatum van de
   app + weekritme). Onbruikbare invoer? Dan de ruwe string."""
    vandaag_date = vandaag_date or datetime.now().date()
    try:
        d = datetime.strptime(str(datum or "")[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return str(datum or "")[:10]
    verschil = (vandaag_date - d).days
    if verschil == 0:
        return "vandaag"
    if verschil == 1:
        return "gisteren"
    if verschil > 1:
        return f"-{verschil} dagen"
    return str(datum)[:10]


def compute_context():
    """Verzamel profiel, metingen, maaltijden en activiteiten tot \u00e9\u00e9n adviescontext."""
    metrics = store.get_metrics(14)
    meals = store.get_meals_today()
    activities = store.get_activities(10)

    # gemiddelde kcal per dag over de laatste 7 dagen (vandaag telt niet mee:
    # die dag is nog niet compleet)
    alle_maaltijden = store.get_meals(300)
    per_dag = {}
    for m in alle_maaltijden:
        dag = (m.get("ts") or "")[:10]
        if dag and dag != store.today():
            per_dag[dag] = per_dag.get(dag, 0) + (m.get("kcal") or 0)
    kcal_avg = None
    waarden = [per_dag[d] for d in sorted(per_dag)][-7:]
    if waarden:
        kcal_avg = round(statistics.mean(waarden))

    def avg(key, n=7):
        vals = [m[key] for m in metrics[-n:] if m.get(key) is not None]
        return round(statistics.mean(vals), 1) if vals else None

    last = metrics[-1] if metrics else {}
    hrv_vals = [m["hrv"] for m in metrics if m.get("hrv") is not None]
    baseline = round(statistics.mean(hrv_vals[-8:-1]), 1) if len(hrv_vals) >= 4 else None
    profile = {k: store.get_setting(k)
               for k in ("age", "sex", "height_cm", "weight_kg", "goal", "step_goal")}
    profile["weight_kg"] = _f(profile.get("weight_kg")) or _f(last.get("weight"))

    return {
        "today": store.today(), "metrics": metrics, "meals": meals,
        "activities": activities, "last": last,
        "steps_avg": avg("steps"), "rhr_avg": avg("resting_hr"),
        "sleep_avg": avg("sleep_hours"), "hrv_avg": avg("hrv"),
        "hrv_baseline": baseline, "kcal_avg_7d": kcal_avg,
        "sleep_last": last.get("sleep_hours"), "hrv_today": last.get("hrv"),
        "rhr_today": last.get("resting_hr"), "stress_today": last.get("stress"),
        "consumed": round(sum(m["kcal"] or 0 for m in meals)),
        "profile": profile,
    }


# ---------------------------------------------------------- regelengine

def rule_readiness(ctx):
    """Trainingsklaarheid 0-100 op basis van HRV, slaap en rusthartslag."""
    score, warnings = 70, []
    if ctx.get("hrv_today") and ctx.get("hrv_baseline"):
        diff = (ctx["hrv_today"] - ctx["hrv_baseline"]) / ctx["hrv_baseline"] * 100
        if diff <= -15:
            score -= 18
            warnings.append(f"HRV ligt {abs(diff):.0f}% onder je basislijn \u2014 onvoldoende herstel.")
        elif diff >= 8:
            score += 10
    if ctx.get("sleep_last"):
        if ctx["sleep_last"] < 6:
            score -= 15
            warnings.append("Kort geslapen (<6 uur) \u2014 beperk vandaag de trainingsintensiteit.")
        elif 7 <= ctx["sleep_last"] <= 8.5:
            score += 6
    if (ctx.get("rhr_today") and ctx.get("rhr_avg")
            and ctx["rhr_today"] > ctx["rhr_avg"] + 4):
        score -= 10
        warnings.append("Rusthartslag verhoogd t.o.v. je gemiddelde \u2014 mogelijk stress of beginnende ziekte.")
    if ctx.get("stress_today") and ctx["stress_today"] > 60:
        score -= 5
    return max(5, min(98, round(score))), warnings


def rule_workout(score, ctx):
    if score < 40:
        return {"type": "Actief herstel (wandelen, mobility of yoga)", "duur_min": 30,
                "intensiteit": "laag",
                "waarom": "Je herstel is nu de beperkende factor; lichte beweging "
                          "versnelt herstel zonder extra belasting."}
    if score < 65:
        return {"type": "Duurtraining in zone 2 (rustig hardlopen of fietsen)", "duur_min": 45,
                "intensiteit": "gemiddeld",
                "waarom": "Bouw aerobe basis op zonder je systeem verder te belasten."}
    if score < 82:
        return {"type": "Tempo-intervallen (bijv. 5 x 3 min op 10 km-tempo)", "duur_min": 55,
                "intensiteit": "gemiddeld-zwaar",
                "waarom": "Je herstel is goed; vandaag levert een kwalitatieve training het meeste op."}
    return {"type": "Zware krachtsessie of HIIT", "duur_min": 60, "intensiteit": "zwaar",
            "waarom": "Topvorm: je lichaam is klaar voor de hoogste belasting van deze week."}


def rule_nutrition(ctx, score):
    """BMR volgens Mifflin-St Jeor, geactiveerd via het stappengemiddelde."""
    p = ctx["profile"]
    weight = _f(p.get("weight_kg")) or 75.0
    age = int(_f(p.get("age")) or 30)
    height = _f(p.get("height_cm")) or 175
    sex = (p.get("sex") or "").lower()
    base = 10 * weight + 6.25 * height - 5 * age
    if sex.startswith("m"):
        bmr = base + 5
    elif sex.startswith("v"):
        bmr = base - 161
    else:
        bmr = base - 78

    steps = ctx.get("steps_avg") or 6000
    factor = 1.3 if steps < 4000 else 1.45 if steps < 8000 else 1.6 if steps < 12000 else 1.75
    goal = (p.get("goal") or "").lower()
    if "afval" in goal:
        tdee = bmr * factor - 350
    elif "aankom" in goal:
        tdee = bmr * factor + 300
    else:
        tdee = bmr * factor

    protein = round(1.8 * weight)
    fat = round(0.9 * weight)
    carbs = max(80, round((tdee - protein * 4 - fat * 9) / 4))
    over = int(round(tdee - (ctx.get("consumed") or 0)))

    tips = []
    if over > 500:
        tips.append("Ruimte voor een eiwitrijke avondmaaltijd met veel groenten.")
    elif over < -200:
        tips.append("Je zit boven je dagdoel; kies vanavond eiwit en groenten boven snelle koolhydraten.")
    if score < 40:
        tips.append("Hersteldag: drink extra water en streef naar 1,6 g eiwit per kg lichaamsgewicht.")
    return {"kcal_doel": int(tdee), "kcal_over": over, "eiwit_g": protein,
            "koolhydraten_g": carbs, "vet_g": fat, "tips": tips}


def rule_tips(ctx):
    tips = []
    if ctx.get("sleep_avg") and ctx["sleep_avg"] < 7:
        tips.append(f"Je slaapgemiddelde is {ctx['sleep_avg']} uur \u2014 "
                    "ga deze week 30-45 minuten eerder naar bed.")
    if ctx.get("steps_avg") and ctx["steps_avg"] < 7000:
        tips.append("Plan dagelijks een wandeling van 20 minuten om richting 8.000 stappen te komen.")
    if (ctx.get("hrv_today") and ctx.get("hrv_baseline")
            and ctx["hrv_today"] < ctx["hrv_baseline"] * 0.9):
        tips.append("Hydrateer extra en plan vandaag bewust rustmomenten in.")
    if not tips:
        tips.append("Blijf consistent: hydrateer, eet eiwitrijk en sta elk uur even op.")
    return tips


def rule_based(ctx):
    score, warnings = rule_readiness(ctx)
    last = ctx.get("last") or {}
    return {"readiness": score, "training": rule_workout(score, ctx),
            "voeding": rule_nutrition(ctx, score), "tips": rule_tips(ctx),
            "waarschuwingen": warnings,
            "basis": {"datum": ctx.get("today"),
                      "hrv": ctx.get("hrv_today"),
                      "slaap_uur": ctx.get("sleep_last"),
                      "rusthf": ctx.get("rhr_today"),
                      "stress": ctx.get("stress_today"),
                      "stappen": last.get("steps"),
                      "stappen_gemiddelde": ctx.get("steps_avg"),
                      "gegeten_kcal": ctx.get("consumed")}}


# ---------------------------------------------------------- AI-traject

def _data_block(ctx, anoniem=None):
    """Datablok voor de prompt. Bij een cloudprovider geanonimiseerd: relatieve
   dagnaam i.p.v. absolute data en het activiteitstype i.p.v. de naam (namen
   bevatten soms een plaats of werk). Lokale Ollama krijgt alles volledig."""
    anoniem = ai_utils.use_api() if anoniem is None else anoniem
    try:
        vandaag_d = datetime.strptime(ctx.get("today"), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        vandaag_d = None
    lines = []
    for m in ctx["metrics"][-7:]:
        dag = rel_dag(m.get("date"), vandaag_d) if anoniem else m.get("date")
        lines.append(f"{dag}: stappen={m.get('steps')}, rustHF={m.get('resting_hr')}, "
                     f"HRV={m.get('hrv')}, slaap={m.get('sleep_hours')}u, "
                     f"gewicht={m.get('weight')}kg, stress={m.get('stress')}")
    acts = []
    for a in ctx["activities"][:7]:
        dist = f", afstand={a['distance_m'] / 1000:.1f} km" if a.get("distance_m") else ""
        typ = (a.get("type") or "?").replace("_", " ")
        duur = round((a.get("duration_s") or 0) / 60)
        statline = (f"{duur} min{dist}, gem-HF={a.get('avg_hr') or '-'}, "
                    f"TE={a.get('aerobic_te') or '-'}")
        if anoniem:
            acts.append(f"{rel_dag((a.get('start_time') or '')[:10], vandaag_d)}: {typ}, {statline}")
        else:
            acts.append(f"{(a.get('start_time') or '')[:10]}: {a.get('name')} ({typ}, {statline})")
    meals = "; ".join(f"{meal['name']} ({int(meal['kcal'] or 0)} kcal)"
                      for meal in ctx["meals"]) or "nog niets gelogd"
    return "\n".join(lines), meals, "\n".join(acts) or "geen"


def _prompt(ctx, fallback, anoniem=None):
    """Prompt opbouwen; anoniem=None volgt de providerkeuze (cloud = anoniem)."""
    metrics_txt, meals_txt, acts_txt = _data_block(ctx, anoniem)
    p = ctx["profile"]
    definitief = {
        "readiness": fallback["readiness"],
        "kcal_doel": fallback["voeding"]["kcal_doel"],
        "kcal_over": fallback["voeding"]["kcal_over"],
        "eiwit_g": fallback["voeding"]["eiwit_g"],
        "koolhydraten_g": fallback["voeding"]["koolhydraten_g"],
        "vet_g": fallback["voeding"]["vet_g"],
    }
    prompt = f"""Analyseer onderstaande gezondheids- en trainingsdata en geef onderbouwd advies voor VANDAAG.

Profiel: leeftijd={p.get('age') or 'onbekend'}, geslacht={p.get('sex') or 'onbekend'}, lengte={p.get('height_cm') or 'onbekend'} cm, gewicht={p.get('weight_kg') or 'onbekend'} kg, doel={p.get('goal') or 'presteren'}, stappendoel={p.get('step_goal') or 'onbekend'}.

Dagmetingen (nieuwste laatste):
{metrics_txt}

Recente activiteiten:
{acts_txt}

Maaltijden vandaag: {meals_txt} (totaal {ctx['consumed']} kcal).
Gemiddelden laatste 7 dagen: stappen {ctx.get('steps_avg')}, rust-HF {ctx.get('rhr_avg')}, slaap {ctx.get('sleep_avg')} uur, HRV {ctx.get('hrv_avg')} ms (basislijn {ctx.get('hrv_baseline')} ms), gemiddeld {ctx.get('kcal_avg_7d')} kcal per dag.

DEFINITIEVE cijfers, reeds berekend met Mifflin-St Jeor x activiteitsfactor, gecorrigeerd voor doel en de maaltijden van vandaag. Neem deze cijfers EXACT over in je JSON:
{json.dumps(definitief, ensure_ascii=False)}

Eisen aan je advies:
- Benut de gemiddelden en trends (slaap, HRV ten opzichte van je basislijn, stappen, kcal per dag) expliciet in je advies en onderbouwing.
- Wees uitgebreid: geef volledige, praktische adviezen in plaats van korte steekwoorden.
- Trainingsadvies past bij de readyheid en herstelmarkers; leg in "waarom" in 3-5 zinnen uit waarom dit type training vandaag het beste past (data, effect op het lichaam, praktische uitvoering).
- Voedingsdoelen zijn consistent met Mifflin-St Jeor en sportvoedingsrichtlijnen (eiwit 1,6-2,2 g/kg/dag).
- De cijfers uit de referentie zijn leidend: verzin geen eigen kcal- of macro-aantallen; in de tips mag je wel tekstueel alternatieve maaltijdide\u00ebn voorstellen.
- Geef 4-6 coachtips die vandaag of deze week direct toepasbaar zijn (concreet: wat, wanneer, hoeveel).
- Geef 4-6 items bij "onderbouwing"; leg per item in 3-6 zinnen uit hoe het lichaam werkt en waarom dit advies daarbij aansluit.
- Wees concreet en persoonlijk; herhaal niet klakkeloos de referentie als je er inhoudelijk iets op vindt.
- Schrijf alsof je het aan een vriend uitlegt die geen sportwetenschapper is: korte zinnen, en vaktermen (zoals HRV, zone 2, TDEE) altijd even in gewone woorden toegelicht.

Antwoord in het Nederlands, uitsluitend als JSON met exact deze structuur:
{{"readiness": <0-100>, "training": {{"type": "...", "duur_min": <int>, "intensiteit": "...", "waarom": "<3-5 volledige zinnen, praktisch en in begrijpelijke taal>"}}, "voeding": {{"kcal_doel": <int>, "kcal_over": <int>, "eiwit_g": <int>, "koolhydraten_g": <int>, "vet_g": <int>, "tips": ["<concrete, toepasbare tips>"]}}, "onderbouwing": [{{"onderwerp": "<kort onderwerp>", "uitleg": "<mechanisme of richtlijn, 3-6 zinnen in gewone woorden>"}}], "tips": ["<4-6 concrete coachtips>"], "waarschuwingen": ["..."]}}"""

    return prompt


def llm_advice(model, ctx, fallback):
    prompt = _prompt(ctx, fallback)
    raw, bron = ai_utils.generate(prompt, system=SYSTEM, model=model, temperature=0.5,
                                  timeout=600, num_ctx=16384, num_predict=3072,
                                  json_mode=True)
    data = ai_utils.extract_json(raw)

    onderbouwing = []
    for item in (data.get("onderbouwing") or [])[:6]:
        if isinstance(item, dict) and item.get("uitleg"):
            onderbouwing.append({"onderwerp": str(item.get("onderwerp") or "Toelichting")[:90],
                                 "uitleg": str(item.get("uitleg"))[:800]})
        elif isinstance(item, str) and item.strip():
            onderbouwing.append({"onderwerp": "Toelichting", "uitleg": item.strip()[:800]})

    # cijfers zijn leidend vanuit de regelengine: deterministisch en model-onafhankelijk
    voeding = dict(fallback["voeding"])
    ai_voeding = data.get("voeding") or {}
    if isinstance(ai_voeding.get("tips"), list) and ai_voeding["tips"]:
        voeding["tips"] = ai_voeding["tips"]
    return {
        "readiness": fallback["readiness"],
        "training": data.get("training") or fallback["training"],
        "voeding": voeding,
        "onderbouwing": onderbouwing,
        "tips": data.get("tips") or fallback["tips"],
        "waarschuwingen": data.get("waarschuwingen") or fallback["waarschuwingen"],
        # de basis-cijfers zijn niet door de AI bepaald maar komen uit de
        # metingen — zonder dit blok stond onderaan een advies met alleen
        # streepjes
        "basis": fallback.get("basis"),
    }, bron


def _first_text_model():
    for name in ai_utils.ollama_models():
        if not any(k in name.lower() for k in ("embed", "bge", "nomic", "minilm", "rerank")):
            return name
    return None


def _first_local_model():
    """Eerste lokale tekstmodel; cloudmodellen (naam eindigt op ':cloud') overslaan,
    die zijn afhankelijk van een account/verbinding en falen vaak stil."""
    for name in ai_utils.ollama_models():
        if name.lower().endswith(":cloud"):
            continue
        if not any(k in name.lower() for k in ("embed", "bge", "nomic", "minilm", "rerank")):
            return name
    return None


def generate(mode=None):
    """Genereer en bewaar het advies.

    mode=None    -> volg de instelling (AI tenzij uitgeschakeld, met fallback)
    mode="ai"    -> forceer AI; mislukt dit, dan AdvisorError (geen stille fallback)
    mode="rules" -> direct de regelengine"""
    ctx = compute_context()
    fallback = rule_based(ctx)
    setting = store.get_setting("model_advice") or "auto"

    want_ai = (mode == "ai") or (mode is None and setting != "uit")
    if not want_ai:
        advice_id = store.save_advice(fallback.get("readiness"), fallback, "Automatische analyse")
        return {"id": advice_id, "source": "Automatische analyse", "note": "", **fallback}

    model = None
    if not ai_utils.use_api():
        model = setting if setting not in ("auto", "", None, "uit") else (_first_local_model() or _first_text_model())
        if not model:
            raise AdvisorError("Geen Ollama-model gevonden \u2014 start Ollama of stel een API in bij Instellingen.")

    try:
        payload, bron = llm_advice(model, ctx, fallback)
        source, note = bron, ""
    except Exception as exc:
        if mode == "ai":
            raise AdvisorError(f"AI-advies mislukt: {exc}") from exc
        payload, source, note = fallback, "Automatische analyse", \
            f"AI niet beschikbaar ({exc}) \u2014 advies van de regelengine."

    payload = {**payload, "note": note}
    advice_id = store.save_advice(payload.get("readiness"), payload, source)
    return {"id": advice_id, "source": source, "note": note, **payload}