#!/usr/bin/env python3
"""
common.py — Utilidades compartidas del Content Engine.

Solo librería estándar (cero pip). Aquí viven:
  - resolución de rutas del proyecto y de cada semana,
  - lectura/escritura atómica de JSON,
  - configuración por defecto del plan,
  - helpers de manifiesto (carga/guardado),
  - localización de una fuente DejaVu para los titulares,
  - mapeo de formato -> dimensiones y de canal -> formato.
"""

import json
import os
import re
import sys
import tempfile

# ---------------------------------------------------------------------------
# Rutas del proyecto
# ---------------------------------------------------------------------------
# engine/common.py  -> ROOT es la carpeta content-engine/
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARCAS_DIR = os.path.join(ROOT, "marcas")
PLANTILLAS_DIR = os.path.join(ROOT, "plantillas")
SEMANAS_DIR = os.path.join(ROOT, "semanas")
PILARES_FILE = os.path.join(ROOT, "pilares.json")


def semana_dir(semana):
    return os.path.join(SEMANAS_DIR, semana)


def paths_semana(semana):
    """Devuelve un dict con las rutas relevantes de una semana."""
    base = semana_dir(semana)
    return {
        "base": base,
        "plan": os.path.join(base, "plan.json"),
        "intencion": os.path.join(base, "intencion.json"),
        "manifest": os.path.join(base, "manifest.json"),
        "calendario": os.path.join(base, "calendario.csv"),
        "inputs_audio": os.path.join(base, "inputs", "audio"),
        "generated": os.path.join(base, "generated"),
        "edited": os.path.join(base, "edited"),
    }


# ---------------------------------------------------------------------------
# Configuración por defecto del plan
# ---------------------------------------------------------------------------
DEFAULT_CONFIG = {
    "formatos": ["9:16"],
    "duracion_toma": 3.5,
    "fps": 30,
    "transicion": 0.5,
    "reintentos": 2,
    "hosts": ["127.0.0.1:8188"],
    "editores": 4,
}

# Formato (relación de aspecto) -> dimensiones de salida.
FORMATO_DIMS = {
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "16:9": (1920, 1080),
    "4:5": (1080, 1350),
}

# Canal de publicación -> formato preferido.
CANAL_FORMATO = {
    "tiktok": "9:16",
    "ig-reels": "9:16",
    "ig-story": "9:16",
    "ig-feed": "1:1",
    "youtube": "16:9",
    "youtube-shorts": "9:16",
    "shorts": "9:16",
    "x": "16:9",
    "linkedin": "1:1",
}


def formato_dims(formato):
    """Dimensiones (w, h) de un formato; cae a 9:16 si es desconocido."""
    return FORMATO_DIMS.get(formato, FORMATO_DIMS["9:16"])


def canal_a_formato(canal):
    return CANAL_FORMATO.get(canal, "9:16")


def merge_config(plan_config):
    cfg = dict(DEFAULT_CONFIG)
    if plan_config:
        cfg.update({k: v for k, v in plan_config.items() if v is not None})
    return cfg


# ---------------------------------------------------------------------------
# IO de JSON (lectura + escritura atómica)
# ---------------------------------------------------------------------------
def load_json(path, default=None):
    if not os.path.exists(path):
        if default is not None:
            return default
        raise FileNotFoundError(path)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    """Escritura atómica: escribe a un temporal y renombra (no corrompe en fallo)."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


# ---------------------------------------------------------------------------
# Manifiesto
# ---------------------------------------------------------------------------
# Estados de la máquina:  plan -> prompt -> generado -> final   (+ error)
ESTADOS = ("plan", "prompt", "generado", "final", "error")


def load_manifest(semana):
    return load_json(paths_semana(semana)["manifest"], default={"config": {}, "piezas": []})


def save_manifest(semana, manifest):
    save_json(paths_semana(semana)["manifest"], manifest)


# ---------------------------------------------------------------------------
# Fuentes para los titulares
# ---------------------------------------------------------------------------
_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]


def find_font():
    """Devuelve la ruta a una fuente para drawtext, o None si no hay ninguna."""
    for p in _FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


# ---------------------------------------------------------------------------
# Texto / plantillas
# ---------------------------------------------------------------------------
_VAR_RE = re.compile(r"\{([a-zA-Z0-9_]+)\}")


def render_vars(texto, vars_dict):
    """Sustituye {var} por su valor. Las variables ausentes se dejan vacías."""
    if not isinstance(texto, str):
        return texto
    return _VAR_RE.sub(lambda m: str(vars_dict.get(m.group(1), "")).strip(), texto)


def slugify(texto, maxlen=40):
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (texto or "").lower()).strip("-")
    return s[:maxlen] or "x"


# ---------------------------------------------------------------------------
# Log sencillo
# ---------------------------------------------------------------------------
def log(msg):
    print(msg, flush=True)


def warn(msg):
    print(f"[aviso] {msg}", file=sys.stderr, flush=True)
