"""engine/llm.py — Único punto de creatividad del estudio (API de Anthropic).

Convierte briefs en piezas y rellena copy con el tono de marca. NADA más usa el
LLM: las imágenes/voz/vídeo siguen por sus motores (ComfyUI/ElevenLabs/OpenAI).

Funciones:
  - info_to_brand(slug, info)   -> dict brand.json (marca/voz/info); marca pendientes
  - brief_to_piece(brand, brief, blueprint=None) -> pieza válida contra el esquema
  - fill_copy(brand, piece)     -> pieza con los huecos de texto rellenos

Ambas pasan ESQUEMA + BRAND como contexto, exigen JSON puro y llevan bucle de
validación/reparación contra schema/production_package.schema.json.

Modelo configurable: brand.generacion.texto.modelo > env ANTHROPIC_MODEL > default.
Clave: env ANTHROPIC_API_KEY (los pasos creativos van por la API de Anthropic;
desde el entorno web api.anthropic.com es alcanzable).
"""
import os, json, sys, copy

SCHEMA_PATH = "schema/production_package.schema.json"
DEFAULT_MODEL = "claude-opus-4-8"
MAX_REPAIR = 3

# Dependencias por formato (para validación de estructura previa al gate real).
# Espejo ligero de FORMAT_DEPS de studio.py; el gate autoritativo corre en `plan`.
_NEEDS = {
    "ugc":          ["avatar.dialogo"],
    "slideshow":    ["imagenes>=2"],
    "before_after": ["imagenes==2"],
    "cinematic":    ["imagen.prompt"], "pov_phone": ["imagen.prompt"],
    "product":      ["imagen.prompt"], "screen_demo": ["imagen.prompt"],
    "hands_asmr":   ["imagen.prompt"],
    "kinetic_text": [], "stat_reveal": [],
}


def _model(brand):
    g = (brand.get("generacion") or {}).get("texto") or {}
    return g.get("modelo") or os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL


def _client():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("⛔ Falta ANTHROPIC_API_KEY en el entorno. Los pasos creativos (brief→pieza, "
                 "rellenar copy) usan la API de Anthropic. Añádela en Settings y abre sesión nueva.")
    import anthropic
    return anthropic.Anthropic()


def _schema():
    return json.load(open(SCHEMA_PATH, encoding="utf-8"))


def _extract_json(text):
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1]
        if t.lstrip().lower().startswith("json"):
            t = t.lstrip()[4:]
    t = t.strip().strip("`").strip()
    # recorta al primer { … último }
    a, b = t.find("{"), t.rfind("}")
    if a >= 0 and b > a:
        t = t[a:b + 1]
    return json.loads(t)


def _call_json(brand, system, user, max_tokens=8000):
    client = _client()
    resp = client.messages.create(
        model=_model(brand), max_tokens=max_tokens,
        thinking={"type": "adaptive"},
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    return _extract_json(text)


# ---------------------------------------------------------------------------
# Validación (esquema + estructura) — devuelve lista de errores (vacía = OK)
# ---------------------------------------------------------------------------
def _validate_package(pkg):
    errs = []
    try:
        import jsonschema
        schema = _schema()
        Validator = jsonschema.validators.validator_for(schema)
        for e in Validator(schema).iter_errors(pkg):
            # solo errores que cuelgan de la PIEZA (los de marca/salida no los puede
            # arreglar el LLM, que solo devuelve la pieza; se reportan en otro sitio).
            if e.absolute_path and e.absolute_path[0] != "piezas":
                continue
            loc = "/".join(str(x) for x in e.absolute_path)
            errs.append(f"esquema [{loc}]: {e.message[:200]}")
    except ImportError:
        pass
    for pieza in pkg.get("piezas", []):
        for seg in pieza.get("segmentos", []):
            sid = seg.get("id", "?"); fmt = seg.get("formato")
            for need in _NEEDS.get(fmt, []):
                if need == "avatar.dialogo" and not (seg.get("avatar") or {}).get("dialogo", "").strip():
                    errs.append(f"segmento {sid} [{fmt}]: falta avatar.dialogo (sin él no hay voz → sin lip-sync)")
                if need == "imagen.prompt" and not (seg.get("imagen") or {}).get("prompt", "").strip():
                    errs.append(f"segmento {sid} [{fmt}]: falta imagen.prompt")
                if need == "imagenes>=2" and len(seg.get("imagenes", [])) < 2:
                    errs.append(f"segmento {sid} [{fmt}]: slideshow necesita >=2 en 'imagenes'")
                if need == "imagenes==2" and len(seg.get("imagenes", [])) != 2:
                    errs.append(f"segmento {sid} [{fmt}]: before_after necesita exactamente 2 en 'imagenes'")
    return errs


def _compose(brand, piece):
    return {
        "marca": brand["marca"], "salida": brand["salida"],
        "generacion": brand.get("generacion", {"imagenes": {}}),
        "personajes": brand.get("personajes", []), "piezas": [piece],
    }


def _repair_loop(brand, system, user, kind="pieza"):
    """Llama al LLM y reintenta corrigiendo si la salida no valida."""
    last_err = None
    for intento in range(1, MAX_REPAIR + 1):
        u = user if intento == 1 else (
            user + f"\n\nLa salida anterior NO validó. Corrige EXACTAMENTE estos errores y "
            f"devuelve SOLO el JSON corregido:\n- " + "\n- ".join(last_err))
        try:
            obj = _call_json(brand, system, u)
        except json.JSONDecodeError as e:
            last_err = [f"JSON inválido: {e}"]; continue
        piece = obj.get("piezas", [obj])[0] if "piezas" in obj else obj
        errs = _validate_package(_compose(brand, piece))
        if not errs:
            return piece
        last_err = errs
    sys.exit(f"⛔ No pude generar una {kind} válida tras {MAX_REPAIR} intentos. Últimos errores:\n- "
             + "\n- ".join(last_err or ["desconocido"]))


# ---------------------------------------------------------------------------
# 1) info -> brand.json
# ---------------------------------------------------------------------------
def info_to_brand(slug, info_text, base=None):
    base = base or {}
    system = (
        "Eres el responsable de marca de un estudio de producción de vídeo. A partir de "
        "información en bruto de una empresa, rellena un brand.json. Devuelve SOLO JSON con "
        "esta forma:\n"
        '{"slug":"...","marca":{"nombre":"...","tagline":"...","paleta":{"primario":"#hex",'
        '"fondo":"#hex","tinta":"#hex"},"fuente":"Inter","estilo_visual":"..."},'
        '"salida":{"aspecto":"9:16","resolucion":[1080,1920],"fps":30,"duracion_objetivo_s":30,'
        '"musica":{"tipo":"...","ruta":"projects/%s/assets/music/bed.mp3"},'
        '"voz_off":{"motor":"elevenlabs","voz_id":"","idioma":"es"}},'
        '"generacion":{"imagenes":{"motor":"openai","modelo":"gpt-image-1","calidad":"medium",'
        '"tamano":"1024x1536"},"texto":{"modelo":"claude-opus-4-8"}},"personajes":[],'
        '"info":{"descripcion":"...","publico":"...","propuesta_valor":["..."],"tono":"...",'
        '"evitar":["..."],"enlaces":[],"notas":[]}}\n'
        "Para datos que NO puedas inferir de la info, pon el string \"PENDIENTE\" (no inventes "
        "voz_id, hex de marca reales, ni enlaces). Mantén el resto coherente con la info dada."
    ) % slug
    user = f"slug: {slug}\n\nINFO EN BRUTO:\n{info_text}"
    if base:
        user += f"\n\nBRAND ACTUAL (mejóralo, no borres lo que ya esté bien):\n{json.dumps(base, ensure_ascii=False)}"
    brand = _call_json({}, system, user, max_tokens=4000)
    brand["slug"] = slug
    return brand


# ---------------------------------------------------------------------------
# 2) brief -> pieza
# ---------------------------------------------------------------------------
def brief_to_piece(brand, brief, blueprint=None):
    schema = json.dumps(_schema(), ensure_ascii=False)
    system = (
        "Eres el guionista de un estudio de producción de vídeo vertical (9:16, 30-60s). "
        "Conviertes un BRIEF en una PIEZA: una secuencia de segmentos, cada uno con su "
        "formato, que se compondrá en un vídeo. Devuelve SOLO el JSON de UNA pieza con la "
        'forma {"id":"...","concepto":"...","gancho":"...","cierre_marca":true,"segmentos":[...]}.\n\n'
        "REGLAS DE DEPENDENCIAS (obligatorias, o el vídeo sale roto):\n"
        "- formato 'ugc'/'ugc_pov' SIEMPRE lleva avatar.dialogo (texto que dirá el personaje) y "
        "referencia un personaje en 'personaje'. Sin diálogo no hay voz → no hay lip-sync.\n"
        "- segmentos narrados (cinematic/pov_phone/product/screen_demo/hands_asmr/slideshow) "
        "llevan 'voz_off' (narración) y los de imagen llevan imagen.prompt.\n"
        "- slideshow lleva 'imagenes' (>=2, cada una {prompt,texto}); before_after lleva 2 imágenes.\n"
        "- los prompts de imagen incorporan el estilo_visual de la marca.\n"
        "- usa SOLO formatos del enum del esquema.\n"
        "Varía planos/acciones; mantén el concepto y la marca. Copy en el idioma de la marca.\n\n"
        f"ESQUEMA (la pieza va dentro de piezas[]):\n{schema}\n\n"
        f"MARCA:\n{json.dumps(brand, ensure_ascii=False)}"
    )
    user = f"BRIEF:\n{brief}"
    if blueprint:
        user += f"\n\nUsa como estructura base este blueprint:\n{json.dumps(blueprint, ensure_ascii=False)}"
    return _repair_loop(brand, system, user, kind="pieza")


# ---------------------------------------------------------------------------
# 3) fill_copy -> rellena solo huecos de texto
# ---------------------------------------------------------------------------
def fill_copy(brand, piece):
    schema = json.dumps(_schema(), ensure_ascii=False)
    system = (
        "Eres el copywriter del estudio. Recibes una PIEZA con huecos de texto vacíos o "
        "marcados 'PENDIENTE' y los rellenas en el tono de la marca, SIN cambiar la estructura "
        "(no añadas ni quites segmentos, no cambies formatos ni ids). Rellena: prompts de "
        "imagen (incorporando estilo_visual), avatar.dialogo en ugc, voz_off en narrados, "
        "texto_pantalla/subtitulos. Devuelve SOLO el JSON de la pieza completa.\n\n"
        f"ESQUEMA:\n{schema}\n\nMARCA:\n{json.dumps(brand, ensure_ascii=False)}"
    )
    user = f"PIEZA A COMPLETAR:\n{json.dumps(piece, ensure_ascii=False)}"
    return _repair_loop(brand, system, user, kind="pieza")
