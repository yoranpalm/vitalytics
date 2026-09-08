"""Hulpjes voor AI-aanroepen: lokaal via Ollama (http://127.0.0.1:11434)
of via een OpenAI-compatibele cloud-API (OpenAI, OpenRouter, DeepSeek, ...)."""
import json
import re
import urllib.error
import urllib.request

from . import store

OLLAMA_URL = "http://127.0.0.1:11434"


def http_json(path, payload=None, timeout=240):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        OLLAMA_URL + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ollama_models(timeout=3):
    """Lijst met geinstalleerde Ollama-modellen (leeg als Ollama niet draait)."""
    try:
        data = http_json("/api/tags", timeout=timeout)
        return [m["name"] for m in data.get("models", []) if m.get("name")]
    except Exception:
        return []


def ollama_generate(model, prompt, system=None, images=None, temperature=0.3, timeout=300,
                    num_ctx=None, num_predict=None):
    """Vraag een lokaal Ollama-model om een JSON-antwoord."""
    options = {"temperature": temperature}
    if num_ctx:
        options["num_ctx"] = num_ctx  # voorkom afgekniakte prompts bij lange analyses
    if num_predict:
        options["num_predict"] = num_predict  # Ollama's standaardlimiet kapt lange adviezen af
    payload = {"model": model, "prompt": prompt, "stream": False, "format": "json",
               "think": False,  # thinking-modellen (bv. qwen3) leveren anders leeg 'response'
               "options": options}
    if system:
        payload["system"] = system
    if images:
        payload["images"] = images
    data = http_json("/api/generate", payload, timeout=timeout)
    text = data.get("response") or ""
    if not text.strip() and data.get("thinking"):
        # sommige Ollama-versies zetten de uitkomst in het thinking-veld
        text = data["thinking"]
    return text


def extract_json(text):
    """Haal het eerste JSON-object uit modeltekst (ook na ```json-fences)."""
    if not text:
        raise ValueError("leeg antwoord van het model")
    text = re.sub(r"```(?:json)?", "", str(text))
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("geen JSON gevonden in het modelantwoord")
    return json.loads(text[start:end + 1])


# ------------------------------------------------------- cloud-API (optioneel)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta"


def _api_settings():
    """None als er geen cloud-API (volledig) is ingesteld, anders de config."""
    provider = store.get_setting("ai_provider") or "ollama"
    key = store.get_setting("ai_api_key") or ""
    model = store.get_setting("ai_model") or ""
    base = store.get_setting("ai_base_url") or ""
    if provider == "openai_compat":
        if not key or not model:
            return None
        return {"kind": "openai_compat", "base_url": base or "https://api.openai.com/v1",
                "api_key": key, "model": model}
    if provider == "gemini":
        if not key or not model:
            return None
        return {"kind": "gemini", "base_url": base or GEMINI_URL,
                "api_key": key, "model": model}
    return None


def use_api():
    """True als er een werkende cloud-API-configuratie staat."""
    return _api_settings() is not None


def active_source(ollama_model=None):
    """Bronlabel voor in de UI, bv. 'Gemini · gemini-2.5-flash'."""
    api = _api_settings()
    if api:
        voorvoegsel = "Gemini" if api["kind"] == "gemini" else "API"
        return f"{voorvoegsel} \u00b7 {api['model']}"
    return f"Ollama \u00b7 {ollama_model or 'auto'}"


def _image_mime(b64):
    """MIME-type raden op basis van de eerste base64-bytes."""
    if b64.startswith("iVBORw0KGgo"):
        return "image/png"
    if b64.startswith("UklGR"):
        return "image/webp"
    return "image/jpeg"


def openai_chat(base_url, api_key, model, prompt, system=None, temperature=0.4,
                max_tokens=2048, timeout=300, images=None):
    """Chat completion via een OpenAI-compatibele API; geeft de antwoordtekst."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    if images:
        content = [{"type": "text", "text": prompt}]
        content += [{"type": "image_url",
                     "image_url": {"url": f"data:{_image_mime(b)};base64,{b}"}}
                    for b in images]
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": prompt})
    body = {"model": model, "messages": messages,
            "temperature": temperature, "max_tokens": max_tokens}
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        raise RuntimeError(f"API-fout {exc.code}: {detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"API niet bereikbaar: {exc.reason}") from exc
    content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "")
    if not content:
        raise RuntimeError("De API gaf een leeg antwoord terug")
    return content


def gemini_generate(base_url, api_key, model, prompt, system=None, temperature=0.4,
                    max_tokens=4096, timeout=300, json_mode=False, images=None):
    """Generatie via de Google Gemini API; geeft de antwoordtekst."""
    parts = [{"text": prompt}]
    parts += [{"inline_data": {"mime_type": _image_mime(b), "data": b}}
              for b in (images or [])]
    generation = {"temperature": temperature, "maxOutputTokens": max_tokens}
    if json_mode:
        generation["responseMimeType"] = "application/json"
    body = {"contents": [{"role": "user", "parts": parts}],
            "generationConfig": generation}
    if system:
        body["system_instruction"] = {"parts": [{"text": system}]}
    url = (f"{base_url.rstrip('/')}/models/{model}:generateContent"
           f"?key={api_key}")
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    import time
    for poging in range(4):  # 503/429 bij Google zijn meestal tijdelijk
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:300]
            except Exception:
                pass
            if exc.code in (429, 503) and poging < 3:
                time.sleep(4 * (poging + 1))
                continue
            raise RuntimeError(f"Gemini-fout {exc.code}: {detail or exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Gemini niet bereikbaar: {exc.reason}") from exc
    text = ""
    try:
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts).strip()
    except (KeyError, IndexError, TypeError):
        text = ""
    if not text:
        reden = ((data.get("candidates") or [{}])[0].get("finishReason")
                 or data.get("error", {}).get("message") or "leeg antwoord")
        raise RuntimeError(f"Gemini gaf geen tekst terug ({reden})")
    return text


def first_local_model():
    """Eerste lokale tekstmodel; sla cloud- en embeddingmodellen over."""
    for name in ollama_models():
        if name.lower().endswith(":cloud"):
            continue
        if not any(k in name.lower() for k in ("embed", "bge", "nomic", "minilm", "rerank")):
            return name
    return None


def generate(prompt, system=None, model=None, temperature=0.3, timeout=300,
             num_ctx=None, num_predict=None, json_mode=False, images=None):
    """Generatie met automatische keuze: cloud-API (OpenAI-compatibel of Gemini)
    indien ingesteld, anders lokaal via Ollama. Mislukt de cloud-API (bijv. quota
    of storing), dan valt de functie automatisch terug op lokaal Ollama.
    Geeft (tekst, bronlabel) terug."""
    api = _api_settings()
    if api:
        voorvoegsel = "Gemini" if api["kind"] == "gemini" else "API"
        try:
            if api["kind"] == "gemini":
                text = gemini_generate(api["base_url"], api["api_key"], api["model"],
                                       prompt, system=system, temperature=temperature,
                                       max_tokens=max(16384, num_predict or 0),
                                       timeout=timeout, json_mode=json_mode, images=images)
            else:
                text = openai_chat(api["base_url"], api["api_key"], api["model"], prompt,
                                   system=system, temperature=temperature,
                                   max_tokens=num_predict or 2048, timeout=timeout,
                                   images=images)
            return text, f"{voorvoegsel} \u00b7 {api['model']}"
        except Exception:
            model_fb = first_local_model()
            if not model_fb:
                raise  # geen lokaal alternatief: geef de oorspronkelijke fout door
    model = model or first_local_model()
    if not model:
        raise RuntimeError("Geen AI-backend beschikbaar - start Ollama of stel een API in bij Instellingen.")
    text = ollama_generate(model, prompt, system=system, temperature=temperature,
                           timeout=timeout, num_ctx=num_ctx, num_predict=num_predict,
                           images=images)
    return text, f"Ollama \u00b7 {model}"