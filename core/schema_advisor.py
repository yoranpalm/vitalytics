"""AI-trainingsadvies bij het weekschema: concrete sessie-opbouw en progressie
per geplande training (sportschool, zwemmen, enz.), in begrijpelijke taal."""
from . import advisor, ai_utils, store

SYSTEM = (
    "Je bent een ervaren trainingswetenschapper, kracht- en zwemcoach. "
    "Antwoord altijd in het Nederlands en uitsluitend met geldige JSON. "
    "Schrijf in heldere, alledaagse taal die beginners meteen begrijpen; "
    "leg vaktermen altijd in gewone woorden uit. "
    "Geef concrete, uitvoerbare sessies die passen bij de opgegeven duur: "
    "bij krachttraining oefeningen met sets en herhalingen, bij zwemmen een "
    "opbouw in meters met rusttijden. "
    "Baseer je op gevestigde principes zoals progressieve overbelasting "
    "(elke week iets zwaarder of langer), supercompensatie (herstel zorgt voor "
    "vooruitgang) en techniek voor intensiteit. "
    "Verzin GEEN studies, auteurs, jaren of DOIs. "
    "Wees eerlijk over onzekerheid en individuele verschillen. "
    "Je advies is educatief en geen medisch advies.")


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


def _model_choice():
    setting = store.get_setting("model_advice") or "auto"
    if setting not in ("auto", "", None, "uit"):
        return setting
    return _first_local_model() or _first_text_model()


def _clean(value, limit):
    text = str(value or "").strip()
    return text[:limit] if text else None


DAGEN = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]


def _sport_historie():
    """Per sport de afgelopen 30 dagen: aantal sessies en de laatste prestatie.
   Zo ziet de AI ook zwem- of krachthistorie zonder dat namen nodig zijn."""
    per = {}
    for a in store.get_activities(30):
        typ = (a.get("type") or "?").replace("_", " ")
        d = per.setdefault(typ, {"n": 0, "laatste": a})
        d["n"] += 1
    if not per:
        return "geen"
    regels = []
    for typ, d in per.items():
        a = d["laatste"]
        duur = int((a.get("duration_s") or 0) / 60)
        afstand = f", laatste afstand {a['distance_m']:.0f} m" if a.get("distance_m") else ""
        hf = f", gem-HF {int(a['avg_hr'])} bpm" if a.get("avg_hr") else ""
        te = f", TE {a['aerobic_te']:.1f}" if a.get("aerobic_te") is not None else ""
        regels.append(f"- {typ}: {d['n']} sessie(s), laatste {duur} min{afstand}{hf}{te}")
    return "\n".join(regels)


def _activiteiten(anoniem=False):
    """Korte historie zodat de AI het niveau kent; bij een cloudprovider
   geanonimiseerd (relatieve data, type i.p.v. naam)."""
    acts = store.get_activities(10)
    if not acts:
        return "geen recente activiteiten bekend"
    lines = []
    for a in acts[:10]:
        datum = (a.get("start_time") or "")[:10]
        typ = (a.get("type") or "?").replace("_", " ")
        duur = int((a.get("duration_s") or 0) / 60)
        afstand = f", {a['distance_m'] / 1000:.1f} km" if a.get("distance_m") else ""
        hf = f", gem-HF {int(a['avg_hr'])} bpm" if a.get("avg_hr") else ""
        te = f", trainings-effect {a['aerobic_te']:.1f}" if a.get("aerobic_te") is not None else ""
        if anoniem:
            lines.append(f"- {advisor.rel_dag(datum)}: {typ}, {duur} min{afstand}{hf}{te}")
        else:
            naam = (a.get("name") or "?")[:40]
            lines.append(f"- {datum}: {naam} ({typ}, {duur} min{afstand}{hf}{te})")
    return "\n".join(lines)


def _context(week, plan, anoniem=False):
    profile = {k: store.get_setting(k) for k in ("age", "sex", "weight_kg", "goal")}
    metrics = store.get_metrics(7)
    metingen = "\n".join(
        f"- {advisor.rel_dag(m.get('date')) if anoniem else m.get('date')}: "
        f"slaap {m.get('sleep_hours') or '?'}, HRV {m.get('hrv') or '?'}, "
        f"stappen {m.get('steps') or '?'}, rust-HF {m.get('resting_hr') or '?'}, "
        f"stress {m.get('stress') or '?'}"
        for m in metrics) or "geen metingen bekend"
    dagen = "\n".join(
        f"- {DAGEN[weekday - 1].capitalize()} (dag {weekday}): {e['sport']}, "
        f"{e['minutes']} minuten"
        for weekday, e in sorted(plan["entries"].items()))
    doel = plan.get("sessions_goal")
    prof = (f"leeftijd={profile.get('age') or 'onbekend'}, "
            f"geslacht={profile.get('sex') or 'onbekend'}, "
            f"gewicht={profile.get('weight_kg') or 'onbekend'} kg, "
            f"doel={profile.get('goal') or 'presteren'}")
    aantal = len(plan["entries"])
    weekkop = "het weekplan voor de komende dagen" if anoniem else f"Weekschema {week}"
    return (f"{weekkop} (weekdoel: "
            f"{doel if doel else 'niet ingesteld'} trainingen per week).\n"
            f"Profiel: {prof}\n"
            f"Geplande trainingen ({aantal} stuks):\n{dagen}\n\n"
            f"Recente activiteiten (hieraan zie je het huidige niveau):\n"
            f"{_activiteiten(anoniem)}\n\n"
            f"Sport-historie laatste 30 dagen (aantal sessies per sport en de\n"
            f"laatste prestatie, met zwemafstanden in meters):\n"
            f"{_sport_historie()}\n\n"
            f"Dagmetingen laatste 7 dagen (slaap, HRV, stress):\n{metingen}\n\n"
            f"Geef per geplande training een concrete sessie-opbouw die binnen de "
            f"duur past en leg uit hoe de gebruiker week na week progressie maakt.")


def _prompt(ctx, aantal):
    return f"""{ctx}

Opdracht:
- "per_dag" moet EXACT {aantal} items bevatten: \u00e9\u00e9n blok per geplande training hierboven, in dezelfde volgorde, met dezelfde dag, sport en duur. Sla er dus geen over en voeg er geen toe.
- Zitten er meerdere sportschoolsessies in de week? Maak ze dan verschillend (bijv. dag A bovenlijf, dag B onderlijf) in plaats van dezelfde oefeningen te herhalen.
- Gebruik de recente activiteiten en de sport-historie om het niveau in te schatten: kies gewichten, tempo's, afstanden en intervalhoeveelheden die aansluiten bij wat de gebruiker al presteert, en bouw vanaf daar rustig op. Zwemsets baseer je op de eerdere zwemafstanden uit de sport-historie (bijv. langzaam opbouwen vanaf de laatste afstand); bestaat er voor een sport in het schema geen historie, zeg dat dan expliciet en begin op beginnersniveau.
- Stem de intensiteit af op de dagmetingen: bij weinig slaap, hoge stress of een dalende HRV kies je lichtere sessies en verplaats je zwaar werk naar betere dagen; bij goede waarden mag er meer bij.
- Voor ELKE training: een concrete sessie-opbouw binnen de opgegeven duur. Sportschool: 6-8 oefeningen met sets, herhalingen en rust. Zwemmen: meters met rusttijden (inwarmen, drills, hoofdblok, uitzwemmen). Andere sporten: praktische opbouw met intensiteit.
- Zeg per sessie kort waarom deze opbouw werkt en hoe de gebruiker hiermee week na week vooruitgang boekt (bijv. elke week iets zwaarder, langer of technisch scherper), met een makkelijkere variant als het te zwaar is.
- Geef daarnaast 3-5 algemene tips voor deze week (herstel, voeding, slaap, techniek).
- Schrijf begrijpelijk: geen jargon zonder uitleg, geen verzonnen studies.

Antwoord uitsluitend als JSON met exact deze structuur:
{{"per_dag": [{{"dag": "<dagnaam>", "sport": "<sport>", "duur_min": <int>, "opbouw": ["<stap 1>", "<stap 2>", "<enz.>"], "waarom": "<2-4 zinnen in gewone taal>", "progressie": "<hoe vooruitgang te boeken, 1-3 zinnen>"}}], "tips": ["<3-5 concrete tips>"]}}"""


def generate(week, gebruiker=""):
    """Genereer het advies voor een week. Geeft (payload, bron) terug;
    gooit een fout als het schema leeg is of de AI niet meewerkt."""
    plan = store.get_training_plan(week, gebruiker)
    if not plan.get("entries"):
        raise ValueError("Er staat nog geen training in het schema voor deze week.")
    model = None
    if not ai_utils.use_api():
        model = _model_choice()
        if not model:
            raise RuntimeError("Geen Ollama-modellen gevonden en geen API ingesteld \u2014 "
                               "start Ollama of stel een API in bij Instellingen.")

    raw, bron = ai_utils.generate(_prompt(_context(week, plan, ai_utils.use_api()), len(plan["entries"])),
                                  system=SYSTEM, model=model, temperature=0.5, timeout=600,
                                  num_ctx=16384, num_predict=2048, json_mode=True)
    data = ai_utils.extract_json(raw)

    per_dag = []
    for item in (data.get("per_dag") or [])[:7]:
        if not isinstance(item, dict):
            continue
        dag = _clean(item.get("dag"), 40) or "Training"
        sport = _clean(item.get("sport"), 40) or ""
        opbouw = [s for s in (_clean(step, 160) for step in (item.get("opbouw") or [])) if s][:8]
        waarom = _clean(item.get("waarom"), 300) or ""
        progressie = _clean(item.get("progressie"), 300) or ""
        if not opbouw and not waarom:
            continue
        try:
            duur = int(item.get("duur_min") or 0)
        except (TypeError, ValueError):
            duur = 0
        per_dag.append({"dag": dag, "sport": sport, "duur_min": duur,
                        "opbouw": opbouw, "waarom": waarom, "progressie": progressie})
    if not per_dag:
        raise ValueError("De AI gaf geen bruikbare sessies terug - probeer het nog eens.")
    tips = [t for t in (_clean(x, 300) for x in (data.get("tips") or [])) if t][:6]
    return {"per_dag": per_dag, "tips": tips}, bron