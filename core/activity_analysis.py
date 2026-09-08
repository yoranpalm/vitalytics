"""Regelgebaseerde analyse per activiteit — zelfde filosofie als de adviesengine:
vaste, uitlegbare regels in plaats van een taalmodel."""

RUN_TYPES = {"running", "trail_running", "treadmill_running"}
BIKE_TYPES = {"cycling", "virtual_ride", "gravel_cycling", "road_biking"}

# activiteiten waarbij vooral de benen werken
BENEN_TYPES = RUN_TYPES | BIKE_TYPES | {"walking", "hiking", "indoor_cycling",
                                        "elliptical", "stair_climbing"}

TYPE_MAP = {
    "running": ("Hardlopen", "\U0001F3C3"),
    "trail_running": ("Trailrun", "\U0001F3C3"),
    "treadmill_running": ("Hardlopen (band)", "\U0001F3C3"),
    "cycling": ("Fietsen", "\U0001F6B4"),
    "virtual_ride": ("Fietsen (indoor)", "\U0001F6B4"),
    "gravel_cycling": ("Gravelbiken", "\U0001F6B4"),
    "road_biking": ("Wielrennen", "\U0001F6B4"),
    "swimming": ("Zwemmen", "\U0001F3CA"),
    "lap_swimming": ("Zwemmen (baan)", "\U0001F3CA"),
    "indoor_cardio": ("Cardio", "\U0001F938"),
    "stair_climbing": ("Trappen", "\U0001F3CB"),
    "indoor_rowing": ("Roeien (indoor)", "\U0001F6A3"),
    "indoor_cycling": ("Fietsen (indoor)", "\U0001F6B4"),
    "walking": ("Wandelen", "\U0001F6B6"),
    "hiking": ("Wandelen", "\U0001F6B6"),
    "strength_training": ("Krachttraining", "\U0001F3CB"),
    "yoga": ("Yoga", "\U0001F9D8"),
    "rowing": ("Roeien", "\U0001F6A3"),
    "elliptical": ("Crosstrainer", "\U0001F3CB"),
    "hiit": ("HIIT", "\u26A1"),
}


def type_label(type_key):
    return TYPE_MAP.get((type_key or "").lower(), ((type_key or "Activiteit").replace("_", " ").capitalize(), "\U0001F3C5"))


# ---------------------------------------------------------- sport-iconen
# Stroke-iconen in dezelfde stijl als de navigatie-iconen (24x24, lijn 2px).

def _icon(paths):
    return ('<svg width="24" height="24" viewBox="0 0 24 24" fill="none" '
            'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
            'stroke-linejoin="round">' + paths + "</svg>")

ROUTE = _icon('<circle cx="6" cy="19" r="3"/>'
              '<path d="M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15"/>'
              '<circle cx="18" cy="5" r="3"/>')
MOUNTAIN = _icon('<path d="m8 3 4 8 5-5 5 15H2L8 3Z"/>')
BIKE = _icon('<circle cx="18.5" cy="17.5" r="3.5"/>'
             '<circle cx="5.5" cy="17.5" r="3.5"/>'
             '<circle cx="15" cy="5" r="1"/>'
             '<path d="M12 17.5V14l-3-3 4-3 2 3h2"/>')
SWIMMER = _icon('<circle cx="16.5" cy="5" r="2"/>'
                '<path d="M14.5 7 5.5 11.5"/>'
                '<path d="M2 15.5c2 2 4 2 6 0s4-2 6 0 4 2 6 0"/>'
                '<path d="M2 20.5c2 2 4 2 6 0s4-2 6 0 4 2 6 0"/>')
DUMBBELL = _icon('<path d="M6.5 6.5v11"/>'
                 '<path d="M17.5 6.5v11"/>'
                 '<path d="M3.5 9.5v5"/>'
                 '<path d="M20.5 9.5v5"/>'
                 '<path d="M6.5 12h11"/>')
BOAT = _icon('<path d="M4 15h16l-1.5 5h-13L4 15Z"/>'
             '<path d="M9 14 16 3"/>'
             '<path d="M15 14 8 3"/>')
FOOTPRINTS = _icon('<path d="M4 16v-2.38C4 11.5 2.97 10.5 3 8c.03-2.72 1.49-6 4.5-6C9.37 2 10 3.8 10 5.5c0 3.11-2 5.66-2 8.68V16a2 2 0 1 1-4 0Z"/>'
                   '<path d="M20 20v-2.38c0-2.12 1.03-3.12 1-5.62-.03-2.72-1.49-5.72-4.5-5.72C14.63 6.28 14 8.2 14 9.9c0 3.11 2 5.66 2 8.68V20a2 2 0 1 0 4 0Z"/>'
                   '<path d="M16 17h4"/>'
                   '<path d="M4 13h4"/>')
MEDITATE = _icon('<circle cx="12" cy="4" r="2"/>'
                 '<path d="M12 6.5v5"/>'
                 '<path d="M9.5 9c-1.8 1-2.8 2.8-3.2 4.8"/>'
                 '<path d="M14.5 9c2 1 3 2.8 3.2 4.8"/>'
                 '<path d="M5.8 19.7c1.2-2.3 3.2-3.5 6.2-3.5s4.8 1.2 6 3.5"/>')
ZAP = _icon('<polygon points="13 2 3 14 12 14 11 22 21 10 13 2"/>')
PULSE = _icon('<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>')
STAIRS = _icon('<path d="M4 20h4v-4h4v-4h4V8h4V4"/>')

TYPE_ICON = {
    "running": ROUTE, "trail_running": MOUNTAIN, "treadmill_running": ROUTE,
    "walking": FOOTPRINTS, "hiking": MOUNTAIN,
    "cycling": BIKE, "virtual_ride": BIKE, "gravel_cycling": BIKE,
    "road_biking": BIKE, "indoor_cycling": BIKE,
    "swimming": SWIMMER, "lap_swimming": SWIMMER,
    "rowing": BOAT, "indoor_rowing": BOAT,
    "strength_training": DUMBBELL,
    "yoga": MEDITATE, "pilates": MEDITATE,
    "indoor_cardio": PULSE, "hiit": ZAP,
    "elliptical": PULSE, "stair_climbing": STAIRS,
}


def type_icon(type_key):
    """Sport-icon in de huisstijl (stroke-svg); neutraal puls-icoon als fallback."""
    return TYPE_ICON.get((type_key or "").lower(), PULSE)


def fmt_duration(sec):
    sec = int(round(sec or 0))
    hours, rest = divmod(sec, 3600)
    minutes, seconds = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d} u"
    return f"{minutes}:{seconds:02d} min"


def fmt_pace(sec_per_km):
    if not sec_per_km or sec_per_km <= 0 or sec_per_km > 3600:
        return None
    return f"{int(sec_per_km) // 60}:{int(sec_per_km) % 60:02d} /km"


def _nl(text):
    """Komma als decimale scheider, zoals het in het Nederlands hoort."""
    return str(text).replace(".", ",")

def spiergroepen(rec):
    """Primaire getrainde spiergroepen, geschat uit het activiteitstype en de
    naam (bv. 'Krachtsessie bovenlichaam'). Geeft {'sleutel': <figuur>,
    'groepen': [..]} of None als er niets zinnigs te zeggen is."""
    type_key = (rec.get("type") or "").lower()
    naam = (rec.get("name") or "").lower()

    if type_key in BENEN_TYPES:
        return {"sleutel": "benen", "groepen": ["Quadriceps", "Hamstrings", "Kuiten"]}
    if type_key in ("swimming", "lap_swimming", "open_water_swimming"):
        return {"sleutel": "volledig", "groepen": ["Schouders", "Rug", "Core", "Benen"]}
    if type_key in ("rowing", "indoor_rowing"):
        return {"sleutel": "volledig", "groepen": ["Rug", "Armen", "Core", "Benen"]}
    if type_key in ("yoga", "pilates"):
        return {"sleutel": "romp", "groepen": ["Core", "Rug", "Schouders"]}
    if type_key in ("indoor_cardio", "hiit"):
        return {"sleutel": "volledig", "groepen": ["Volledig lichaam"]}

    if (type_key == "strength_training" or "kracht" in naam
            or "circuit" in naam or "strength" in naam):
        if any(k in naam for k in ("volledig", "full body", "full-body", "heel lichaam")):
            return {"sleutel": "volledig", "groepen": ["Volledig lichaam"]}
        if any(k in naam for k in ("been", "leg", "squat", "lunge",
                                   "quadriceps", "hamstring")):
            return {"sleutel": "benen", "groepen": ["Quadriceps", "Hamstrings", "Billen"]}
        if any(k in naam for k in ("rug", "back", "row", "pull")):
            return {"sleutel": "bovenlichaam", "groepen": ["Rug", "Biceps", "Schouders"]}
        if any(k in naam for k in ("borst", "chest", "bench", "push")):
            return {"sleutel": "bovenlichaam", "groepen": ["Borst", "Triceps", "Schouders"]}
        if any(k in naam for k in ("bovenlichaam", "upper", "arm", "biceps",
                                   "triceps", "schouder", "shoulder")):
            return {"sleutel": "bovenlichaam", "groepen": ["Armen", "Schouders"]}
        if any(k in naam for k in ("core", "buik", "abs", "plank")):
            return {"sleutel": "romp", "groepen": ["Core"]}
        # generieke naam (bv. 'Strength') — standaard bovenlichaam
        return {"sleutel": "bovenlichaam", "groepen": ["Borst", "Schouders", "Armen"]}
    return None


# regio's van het lichaam-figuur: (spiergroep, x, y, breedte, hoogte, hoekradius)
_SP_REGIONS = [
    ("armen", 26, 30, 9, 36, 4.5),
    ("armen", 65, 30, 9, 36, 4.5),
    ("borst", 38, 28, 24, 17, 5),
    ("romp", 38, 47, 24, 21, 5),
    ("quads", 38.5, 72, 10, 28, 5),
    ("quads", 51.5, 72, 10, 28, 5),
    ("kuiten", 40, 104, 7, 26, 3.5),
    ("kuiten", 53, 104, 7, 26, 3.5),
]

# welke regio's oplichten per figuur-sleutel
SPIER_AAN = {
    "bovenlichaam": {"armen", "borst"},
    "romp": {"romp"},
    "benen": {"quads", "kuiten"},
    "volledig": {"armen", "borst", "romp", "quads", "kuiten"},
}


def spieren_svg(key):
    """Lichaam-figuur (svg) met de getrainde spiergroepen gemarkeerd."""
    aan = SPIER_AAN.get(key, set())

    def region(groep, x, y, w, h, rx):
        cls = "sp aan" if groep in aan else "sp"
        return f'<rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}"/>'

    return ('\u003csvg class="spieren-figuur" viewBox="22 2 56 132" role="img" '
            'aria-label="Lichaam met gemarkeerde getrainde spiergroepen">'
            '<circle class="sp" cx="50" cy="15" r="9"/>'
            + "".join(region(*r) for r in _SP_REGIONS) + "</svg>")


def _te_label(ate):
    if ate is None:
        return None
    v = f"{ate:.1f}".replace(".", ",")
    if ate < 1:
        return f"{v} \u00b7 minimaal effect"
    if ate < 2:
        return f"{v} \u00b7 herstelwerking"
    if ate < 3:
        return f"{v} \u00b7 onderhoudend"
    if ate < 4:
        return f"{v} \u00b7 verbeterend"
    if ate < 5:
        return f"{v} \u00b7 sterk verbeterend"
    return f"{v} \u00b7 overdreven \u2014 let op opbouw"


def _te_uitleg(ate):
    """Uitleg bij het aerobe trainingseffect, in gewone mensentaal."""
    if ate is None:
        return None
    if ate < 1:
        return ("Deze sessie was heel licht: je lichaam hoefde zich nauwelijks aan te "
                "passen. Ideaal voor een rustdag, of gewoon om lekker in beweging te zijn.")
    if ate < 2:
        return ("Dit was vooral een herstelsessie: goed voor je lichaam, maar het daagde "
                "je niet echt uit. Precies wat je nodig hebt op een rustige dag.")
    if ate < 3:
        return ("Een degelijke training die je huidige conditie op peil houdt. Niet zwaar, "
                "wel nuttig \u2014 vooral als je dit regelmatig doet.")
    if ate < 4:
        return ("Een stevige training die je conditie echt verbetert. Je merkt dat vooral "
                "aan de dag erna: door dan rustig aan te doen, word je sterker.")
    if ate < 5:
        return ("Een zware training die je conditie flink verbetert. Geef je lichaam 1 \u00e0 2 "
                "rustigere dagen om dit te verwerken \u2014 daar word je sterker van.")
    return ("Een heel zware training, zwaarder dan je lichaam in \u00e9\u00e9n keer kan verwerken. "
            "Bouw dit soort sessies langzaam op en plan er rustige dagen na.")


def analyse_activity(rec, peer_paces, profile):
    """Analyseer een activiteit in begrijpelijke taal. peer_paces = tempo's (s/km) van
    eerdere activiteiten van hetzelfde type; profile = {'age': int|None}.
    Levert 'punten' als lijst van {'label', 'tekst'} voor een opgeruimde weergave."""
    type_key = (rec.get("type") or "").lower()
    label, emoji = type_label(type_key)
    icon = type_icon(type_key)
    duration = rec.get("duration_s") or 0
    distance = rec.get("distance_m") or 0
    duration_min = duration / 60
    punten = []

    # duur
    if duration_min < 20:
        dur_txt = "een korte sessie \u2014 prima voor een drukke dag"
    elif duration_min < 45:
        dur_txt = "een degelijke training van gemiddelde lengte"
    elif duration_min < 90:
        dur_txt = "een stevige training waar je tijd voor nam"
    else:
        dur_txt = "een echte lange sessie \u2014 knap dat je dit volhield"
    punten.append({"label": "Duur",
                   "tekst": f"Je was {fmt_duration(duration)} onderweg: {dur_txt}."})

    # hartslag-intensiteit (Tanaka: HRmax \u2248 208 - 0,7 \u00d7 leeftijd)
    avg_hr = rec.get("avg_hr")
    age = int(profile.get("age") or 0)
    intensity_pct = None
    if avg_hr and age:
        hr_max = 208 - 0.7 * age
        intensity_pct = avg_hr / hr_max * 100
        if intensity_pct < 60:
            zone_txt = "heel rustig \u2014 ideaal om te herstellen of gewoon lekker buiten te zijn"
        elif intensity_pct < 70:
            zone_txt = ("een rustig tempo waarin je conditie gestaag groeit, zonder dat je "
                        "lichaam overbelast wordt")
        elif intensity_pct < 80:
            zone_txt = "flink werken \u2014 dit maakt je uithoudingsvermogen merkbaar sterker"
        elif intensity_pct < 90:
            zone_txt = ("zwaar \u2014 je hebt flink je best gedaan. Dit maakt je sneller, maar "
                        "je lichaam heeft daarna rust nodig")
        else:
            zone_txt = "zeer zwaar \u2014 dat houd je alleen vol bij een wedstrijd of een test"
        punten.append({
            "label": "Hartslag",
            "tekst": f"Je hart sloeg gemiddeld {int(avg_hr)} keer per minuut, ongeveer "
                     f"{intensity_pct:.0f}% van je geschatte maximum "
                     f"({_nl(f'{hr_max:.0f}')} slagen per minuut). Dat was {zone_txt}."})

    # tempo / snelheid, met vergelijking tegen eerdere activiteiten van dit type
    pace_now = None
    vergelijking = None
    if type_key in RUN_TYPES and distance > 0:
        pace_now = duration / (distance / 1000)
        pace_txt = fmt_pace(pace_now)
        if pace_txt:
            punten.append({"label": "Tempo",
                           "tekst": f"Je deed gemiddeld {pace_txt} per kilometer over "
                                    f"{_nl(f'{distance / 1000:.2f}')} km."})
    elif type_key in BIKE_TYPES and distance > 0 and duration > 0:
        speed = (distance / 1000) / (duration / 3600)
        pace_now = 3600 / speed if speed > 0 else None
        punten.append({"label": "Tempo",
                       "tekst": f"Je reed gemiddeld {_nl(f'{speed:.1f}')} km/u over "
                                f"{_nl(f'{distance / 1000:.1f}')} km."})

    if pace_now and peer_paces:
        peer_avg = sum(peer_paces) / len(peer_paces)
        delta = (pace_now - peer_avg) / peer_avg * 100
        faster_is = -1 if type_key in RUN_TYPES else 1  # bij fietsen is hogere snelheid sneller
        if delta * faster_is <= -3:
            vergelijking = ("Dit ging duidelijk sneller dan je meestal doet \u2014 een echte "
                            "topsessie. Neem de dag erna wat rustiger.")
        elif delta * faster_is < -0.5:
            vergelijking = "Dat lag wat sneller dan je gemiddelde: lekker gelopen."
        elif delta * faster_is <= 0.5:
            vergelijking = "Dat is precies in lijn met wat je gewend bent."
        elif delta * faster_is <= 3:
            vergelijking = "Dat lag wat rustiger dan je gemiddelde."
        else:
            vergelijking = ("Dit ging duidelijk rustiger dan je meestal doet \u2014 prima "
                            "herstelwerk: beweging zonder extra stress voor je lichaam.")
        punten.append({"label": "Vergelijking", "tekst": vergelijking})

    # pasfrequentie (hardlopen)
    cadence = rec.get("avg_cadence")
    if type_key in RUN_TYPES and cadence:
        if cadence >= 170:
            cad_txt = (f"Je voeten landden gemiddeld {int(cadence)} keer per minuut \u2014 een "
                       f"vlotte, effici\u00ebnte pas met minder kans op blessures.")
        elif cadence >= 160:
            cad_txt = (f"Je voeten landden gemiddeld {int(cadence)} keer per minuut \u2014 prima. "
                       f"Wil je n\u00f3g soepeler lopen? Richt op iets kortere, snellere passen "
                       f"(richting 170 per minuut).")
        else:
            cad_txt = (f"Je voeten landden gemiddeld {int(cadence)} keer per minuut \u2014 dat is "
                       f"aan de rustige kant. Iets kortere, snellere passen (richting 170 per "
                       f"minuut) belasten je knie\u00ebn en enkels minder.")
        punten.append({"label": "Loopstijl", "tekst": cad_txt})

    # trainingseffect
    ate = rec.get("aerobic_te")
    te_label = _te_label(ate)
    te_uitleg = _te_uitleg(ate)
    if te_uitleg:
        tekst = te_uitleg
        at = rec.get("anaerobic_te")
        if at and at >= 2:
            tekst += (" Ook het korte, explosieve werk kwam goed aan bod \u2014 neem de dag "
                      "erna een beetje rustiger.")
        punten.append({"label": "Effect", "tekst": tekst})

    # calorie\u00ebn
    calories = rec.get("calories")
    if calories and duration_min > 0:
        per_min = calories / duration_min
        if per_min >= 12:
            kcal_txt = (f"Je verbrandde ongeveer {int(calories)} calorie\u00ebn "
                        f"({_nl(f'{per_min:.0f}')} per minuut) \u2014 dat is veel. Eet binnen een "
                        f"uurtje iets eiwitrijks om goed te herstellen.")
        elif per_min >= 7:
            kcal_txt = (f"Je verbrandde ongeveer {int(calories)} calorie\u00ebn "
                        f"({_nl(f'{per_min:.0f}')} per minuut) \u2014 een stevige inspanning.")
        else:
            kcal_txt = (f"Je verbrandde ongeveer {int(calories)} calorie\u00ebn "
                        f"({_nl(f'{per_min:.0f}')} per minuut) \u2014 een rustige inspanning.")
        punten.append({"label": "Calorie\u00ebn", "tekst": kcal_txt})

    # eindoordeel
    if ate is not None and ate >= 4:
        verdict = ("Zware training \u2014 neem de komende 1 \u00e0 2 dagen wat rustiger aan; "
                   "daar word je sterker van.")
    elif ate is not None and ate >= 3:
        verdict = "Sterke training \u2014 deze duwt je conditie duidelijk vooruit."
    elif ate is not None and ate >= 2:
        verdict = "Degelijke training \u2014 houdt je conditie op peil."
    elif intensity_pct and intensity_pct < 70:
        verdict = "Rustige training \u2014 goed voor je herstel, zonder extra belasting."
    else:
        verdict = "Stevige training \u2014 zorg voor genoeg drinken en rust erna."
    if vergelijking and vergelijking.startswith("Dit ging duidelijk sneller"):
        verdict = ("Topsessie \u2014 duidelijk sneller dan je gemiddelde; vandaag mag je "
                   "extra rusten.")

    # samenvatting voor de kaart
    distance_txt = "\u2013"
    if distance >= 1000:
        distance_txt = _nl(f"{distance / 1000:.1f} km")
    elif distance > 0:
        distance_txt = f"{int(distance)} m"

    tempo_txt = "\u2013"
    if type_key in RUN_TYPES and distance > 0:
        pace_txt = fmt_pace(duration / (distance / 1000))
        if pace_txt:
            tempo_txt = pace_txt
    elif type_key in BIKE_TYPES and distance > 0 and duration > 0:
        tempo_txt = _nl(f"{(distance / 1000) / (duration / 3600):.1f} km/u")

    # trainingsscore: de hoogste trainingseffect-waarde (a\u00ebroob of ana\u00ebroob, 0-5)
    effect_scores = [v for v in (ate, rec.get("anaerobic_te")) if v is not None]
    score_txt = _nl(f"{max(effect_scores):.1f}") if effect_scores else "\u2013"

    spieren = spiergroepen(rec)
    if spieren:
        spieren["figuur"] = spieren_svg(spieren["sleutel"])

    return {
        "emoji": emoji,
        "icon": icon,
        "type_label": label,
        "duur": fmt_duration(duration),
        "afstand": distance_txt,
        "tempo": tempo_txt,
        "te_label": te_label or "\u2013",
        "verdict": verdict,
        "punten": punten,
        "spieren": spieren,
        "score": score_txt,
    }