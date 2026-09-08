"""AI-gezondheidsanalyse bovenop het dashboard: korte tekst met wat er goed
gaat en wat beter kan, op basis van zoveel mogelijk Garmin-metingen,
activiteiten en maaltijden van de afgelopen dagen.

Wordt ververst bij elke geslaagde Garmin-sync en bewaard in de instellingen-
tabel zodat het dashboard hem direct kan tonen. Zonder AI (of bij fouten)
valt de module terug op een regelgebaseerde samenvatting - dezelfde
filosofie als de adviesengine."""
import json

from . import advisor, ai_utils, store


def huidige():
    """Laatst opgeslagen dashboardsamenvatting (dict) of None."""
    try:
        data = json.loads(store.get_setting("dash_summary") or "")
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("samenvatting") else None


def _maaltijd_blok(anoniem=False):
    """Maaltijden per dag (laatste 7 gelogde dagen) als leesbare regels; bij een
   cloudprovider met relatieve dagnaam i.p.v. absolute data."""
    dagen = {}
    for m in store.get_meals(300):
        dag = (m.get("ts") or "")[:10]
        if not dag:
            continue
        d = dagen.setdefault(dag, {"items": [], "kcal": 0.0, "protein": 0.0,
                                   "carbs": 0.0, "fat": 0.0})
        d["items"].append(f"{m.get('name')} ({int(m.get('kcal') or 0)} kcal, "
                          f"E{int(m.get('protein') or 0)} K{int(m.get('carbs') or 0)} "
                          f"V{int(m.get('fat') or 0)})")
        for k in ("kcal", "protein", "carbs", "fat"):
            d[k] += m.get(k) or 0
    regels = []
    for dag in sorted(dagen)[-7:]:
        d = dagen[dag]
        label = advisor.rel_dag(dag) if anoniem else dag
        regels.append(f"{label}: {'; '.join(d['items'][:6])} - dagtotaal "
                      f"{int(d['kcal'])} kcal (E{int(d['protein'])} "
                      f"K{int(d['carbs'])} V{int(d['fat'])})")
    return "\n".join(regels) or "geen maaltijden gelogd"


def _data_blok(ctx, anoniem=False):
    """Alle relevante data (metingen, activiteiten, profiel) als prompttekst;
   bij een cloudprovider geanonimiseerd (relatieve data, type i.p.v. naam)."""
    regels = []
    for m in ctx["metrics"][-14:]:
        dag = advisor.rel_dag(m.get("date")) if anoniem else m.get("date")
        regels.append(f"{dag}: stappen={m.get('steps')}, rustHF={m.get('resting_hr')}, "
                      f"HRV={m.get('hrv')}, slaap={m.get('sleep_hours')}u, "
                      f"gewicht={m.get('weight')}kg, stress={m.get('stress')}")
    metingen = "\n".join(regels) or "geen metingen"

    acts = []
    for a in store.get_activities(10):
        dist = f", {a['distance_m'] / 1000:.1f} km" if a.get("distance_m") else ""
        typ = (a.get("type") or "?").replace("_", " ")
        duur = round((a.get("duration_s") or 0) / 60)
        dag = advisor.rel_dag((a.get("start_time") or "")[:10]) if anoniem else (a.get("start_time") or "")[:10]
        if anoniem:
            acts.append(f"{dag}: {typ}, {duur} min{dist}")
        else:
            acts.append(f"{dag}: {a.get('name')} ({typ}, {duur} min{dist})")
    activiteiten = "\n".join(acts) or "geen"

    p = ctx["profile"]
    profiel = (f"leeftijd={p.get('age') or 'onbekend'}, "
               f"geslacht={p.get('sex') or 'onbekend'}, "
               f"lengte={p.get('height_cm') or 'onbekend'} cm, "
               f"gewicht={p.get('weight_kg') or 'onbekend'} kg, "
               f"doel={p.get('goal') or 'presteren'}, "
               f"stappendoel={p.get('step_goal') or 'onbekend'}")
    return metingen, activiteiten, profiel


def _fallback(ctx):
    """Regelgebaseerde samenvatting - zelfde structuur als de AI-uitvoer."""
    score, waarschuwingen = advisor.rule_readiness(ctx)
    gaat, beter = [], []

    slaap = ctx.get("sleep_avg")
    if slaap and slaap >= 7:
        gaat.append(f"Slaap is goed op orde: gemiddeld {slaap} uur per nacht.")
    elif slaap:
        beter.append(f"Slaapgemiddelde is {slaap} uur - richt op 7,5 tot 8,5 uur "
                     "door eerder naar bed te gaan.")

    stappen = ctx.get("steps_avg")
    if stappen and stappen >= 8000:
        gaat.append(f"Ruim voldoende beweging: gemiddeld {int(stappen)} stappen per dag.")
    elif stappen:
        beter.append(f"Stappengemiddelde is {int(stappen)} - een dagelijkse wandeling "
                     "van 20-30 minuten brengt je richting 8.000.")

    hrv_vandaag, hrv_basis = ctx.get("hrv_today"), ctx.get("hrv_baseline")
    if hrv_vandaag and hrv_basis:
        if hrv_vandaag >= hrv_basis * 0.98:
            gaat.append("Herstel is op orde: HRV ligt rond je basislijn.")
        else:
            beter.append("HRV ligt onder je basislijn - houd vandaag rustig aan "
                         "beweging en plan een vroege avond.")

    rhr_vandaag, rhr_gem = ctx.get("rhr_today"), ctx.get("rhr_avg")
    if rhr_vandaag and rhr_gem and rhr_vandaag > rhr_gem + 4:
        beter.append("Rusthartslag is verhoogd t.o.v. je gemiddelde - mogelijk "
                     "stress of vermoeidheid; hou het vandaag rustig.")
    for w in waarschuwingen:
        if w not in beter:
            beter.append(w)

    if not gaat:
        gaat.append("De data wordt nog opgebouwd; sync Garmin en log maaltijden "
                    "voor een vollediger beeld.")
    if not beter:
        beter.append("Geen grote aandachtspunten: houd consistentie vast in "
                     "slaap, beweging en voeding.")

    samenvatting = (f"Trainingsklaarheid vandaag {score}/100. "
                    f"Slaapgemiddelde {slaap or '?'} uur, stappen gemiddeld "
                    f"{int(stappen) if stappen else '?'} per dag. "
                    "Hieronder de punten die opvallen uit je recente data.")
    return {"samenvatting": samenvatting, "gaat_goed": gaat[:4], "kan_beter": beter[:4]}


PROMPT = """Analyseer de gezondheids- en voedingsdata hieronder en geef een korte,
persoonlijke analyse voor VANDAAG.

Profiel: {profiel}

Dagmetingen Garmin (nieuwste laatste):
{metingen}

Recente activiteiten:
{activiteiten}

Maaltijden per dag (laatste 7 gelogde dagen):
{maaltijden}

Gemiddelden laatste 7 dagen: stappen {stappen}, rust-HF {rhr}, slaap {slaap} uur,
HRV {hrv} ms (basislijn {hrv_basis} ms), gemiddeld {kcal_avg} kcal per dag gegeten.

Eisen:
- Noem concrete cijfers uit de data in je punten; vermijd algemene
  leefstijlplatitudes zonder cijfers of aanleiding.
- "samenvatting": 2-4 zinnen die de hoofdlijn schets (hoe gaat het overall,
  wat valt op deze week).
- "gaat_goed" en "kan_beter": elk punt is hooguit één korte zin van maximaal
  15 woorden - de punten verschijnen als compacte opsomming op het dashboard,
  dus geen lange zinnen of meerdere zinnen per punt.
- "kan_beter": 2-4 concrete, uitvoerbare punten met aanleiding (welke meting, welke afwijking). Formuleer als coach, niet als doktersvoorschrift.

Antwoord in het Nederlands, uitsluitend als JSON met exact deze structuur:
{{"samenvatting": "<2-4 zinnen>", "gaat_goed": ["..."], "kan_beter": ["..."]}}"""


def _model_keuze():
    """Ingesteld model bij lokale Ollama; None bij een cloud-API."""
    if ai_utils.use_api():
        return None
    setting = store.get_setting("model_advice")
    if setting not in ("auto", "", None, "uit"):
        return setting
    return advisor._first_local_model() or advisor._first_text_model()


def generate():
    """Genereer de dashboardsamenvatting en bewaar hem; geeft het payload terug.
    Faalt de AI, dan komt er altijd een regelgebaseerde variant in de plaats."""
    ctx = advisor.compute_context()
    fallback = _fallback(ctx)
    payload, bron = fallback, "Automatische analyse"

    if store.get_setting("model_advice") != "uit":
        anoniem = ai_utils.use_api()
        metingen, activiteiten, profiel = _data_blok(ctx, anoniem)
        prompt = PROMPT.format(
            profiel=profiel, metingen=metingen,
            activiteiten=activiteiten, maaltijden=_maaltijd_blok(anoniem),
            stappen=ctx.get("steps_avg"), rhr=ctx.get("rhr_avg"),
            slaap=ctx.get("sleep_avg"), hrv=ctx.get("hrv_avg"),
            hrv_basis=ctx.get("hrv_baseline"), kcal_avg=ctx.get("kcal_avg_7d"))
        try:
            raw, ai_bron = ai_utils.generate(
                prompt, system=advisor.SYSTEM, model=_model_keuze(),
                temperature=0.4, timeout=240, num_ctx=16384, num_predict=1024,
                json_mode=True)
            data = ai_utils.extract_json(raw)
            goed = [str(x).strip()[:300] for x in (data.get("gaat_goed") or [])
                    if str(x).strip()][:4]
            beter = [str(x).strip()[:300] for x in (data.get("kan_beter") or [])
                     if str(x).strip()][:4]
            tekst = str(data.get("samenvatting") or "").strip()[:1200]
            if tekst and (goed or beter):
                payload = {"samenvatting": tekst, "gaat_goed": goed, "kan_beter": beter}
                bron = ai_bron
        except Exception as exc:
            bron = f"Automatische analyse (AI onbeschikbaar: {str(exc)[:90]})"

    payload = {**payload, "bron": bron, "ts": store.now()}
    store.set_setting("dash_summary", json.dumps(payload, ensure_ascii=False))
    return payload
