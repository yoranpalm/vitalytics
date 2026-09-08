"""Analyse van maaltijdfoto's met AI: via de ingestelde provider (Gemini of
OpenAI-compatibel in de cloud, of lokaal Ollama met een vision-model zoals
llava, llama3.2-vision, qwen2.5vl of gemma3)."""
import base64

from . import ai_utils

VISION_KEYWORDS = ("llava", "vision", "vl", "gemma3", "moondream", "minicpm")

PROMPT = """Je bent een voedingsdeskundige. Analyseer deze maaltijdfoto en schat de portiegrootte mee.
Antwoord uitsluitend met JSON met exact deze structuur:
{"naam": "korte naam van het gerecht", "kcal": <getal>, "eiwit": <gram>, "koolhydraten": <gram>, "vet": <gram>, "portie_g": <gram>}
Antwoord in het Nederlands."""

TEXT_PROMPT = """Je bent een voedingsdeskundige. Schat de voedingswaarden van deze omschreven maaltijd.
Ga bij genoemde hoeveelheden uit van wat er staat, en anders van een gemiddelde volwassen portie.
Antwoord uitsluitend met JSON met exact deze structuur:
{"naam": "korte naam van het gerecht", "kcal": <getal>, "eiwit": <gram>, "koolhydraten": <gram>, "vet": <gram>, "portie_g": <gram>}
Antwoord in het Nederlands."""


def pick_vision_model(models):
    """Kies automatisch het meest geschikte vision-model uit een modellenlijst."""
    for kw in VISION_KEYWORDS:
        for name in models:
            if kw in name.lower():
                return name
    return None


def analyze_photo(image_bytes):
    """Analyseer maaltijdfoto-bytes met AI. Geeft (schattingen, bron) terug."""
    b64 = base64.b64encode(image_bytes).decode("ascii")
    if ai_utils.use_api():
        raw, bron = ai_utils.generate(PROMPT, images=[b64], temperature=0.2,
                                      timeout=420, json_mode=True, num_predict=700)
    else:
        model = pick_vision_model(ai_utils.ollama_models())
        if not model:
            raise RuntimeError("Geen lokaal vision-model gevonden (installeer bijv. "
                               "llava of gemma3 via Ollama) en er is geen cloud-API ingesteld.")
        raw, bron = ai_utils.generate(PROMPT, model=model, images=[b64],
                                      temperature=0.2, timeout=420, json_mode=True,
                                      num_predict=700)
    return _coerce(ai_utils.extract_json(raw)), bron


def estimate_text(beschrijving):
    """Schat naam en voedingswaarden op basis van een tekstomschrijving (zelfde
    schema als de foto-analyse). Geeft (schattingen, bron) terug."""
    raw, bron = ai_utils.generate(
        f"{TEXT_PROMPT}\n\nOmschrijving: {beschrijving.strip()}",
        temperature=0.2, timeout=180, json_mode=True, num_predict=400)
    return _coerce(ai_utils.extract_json(raw)), bron


def _num(value):
    try:
        return round(float(str(value).replace(",", ".")), 1)
    except (TypeError, ValueError):
        return None


def _coerce(data):
    """Modelantwoord defensief omzetten naar ons veldenschema."""
    return {
        "naam": str(data.get("naam") or data.get("name") or "Onbekende maaltijd")[:120],
        "kcal": _num(data.get("kcal") or data.get("calories")),
        "eiwit": _num(data.get("eiwit") or data.get("protein")),
        "koolhydraten": _num(data.get("koolhydraten") or data.get("carbs")
                             or data.get("carbohydrates")),
        "vet": _num(data.get("vet") or data.get("fat")),
        "portie_g": _num(data.get("portie_g") or data.get("portie")),
    }