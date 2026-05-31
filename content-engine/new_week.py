#!/usr/bin/env python3
"""
new_week.py — Crea una semana del Content Engine.

    python3 new_week.py 2026-W23

Crea semanas/<W>/ con sus subcarpetas (inputs/audio, generated, edited) y un
plan.json + intencion.json de arranque para que puedas editarlos. La PRIMERA vez
(si no existen) siembra también los ejemplos compartidos del proyecto:
  - marcas/default/  (estilo.json, workflow.json en formato API, workflow.map.json)
  - plantillas/*.json
  - pilares.json

Este archivo es la única fuente de verdad de los ejemplos: si borras alguno y
vuelves a crear una semana, se regenera.
"""

import os
import sys

# Permite ejecutar como `python3 new_week.py` desde content-engine/.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from common import (  # noqa: E402
    MARCAS_DIR, PLANTILLAS_DIR, PILARES_FILE, paths_semana,
    load_json, save_json, log,
)


# ---------------------------------------------------------------------------
# Ejemplos: marca "default"
# ---------------------------------------------------------------------------
ESTILO_DEFAULT = {
    "descripcion": "Marca de ejemplo. Ajusta sufijo_prompt / negativo / resolucion a tu estilo visual.",
    "vars": {"estilo": "fotografía limpia, iluminación suave de estudio, paleta neutra"},
    "sufijo_prompt": "alta calidad, gran nitidez, composición profesional, 8k",
    "negativo": "baja calidad, borroso, deforme, texto, marca de agua, logo, manos extra",
    "resolucion": [1024, 1024],
}

# Workflow SDXL text2img en FORMATO API de ComfyUI. Sustitúyelo por el tuyo
# (Settings -> Dev mode -> Save API Format) y actualiza workflow.map.json.
WORKFLOW_DEFAULT = {
    "4": {"class_type": "CheckpointLoaderSimple",
          "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"}},
    "5": {"class_type": "EmptyLatentImage",
          "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
    "6": {"class_type": "CLIPTextEncode",
          "inputs": {"text": "", "clip": ["4", 1]}, "_meta": {"title": "positive"}},
    "7": {"class_type": "CLIPTextEncode",
          "inputs": {"text": "", "clip": ["4", 1]}, "_meta": {"title": "negative"}},
    "3": {"class_type": "KSampler",
          "inputs": {"seed": 0, "steps": 25, "cfg": 7.0, "sampler_name": "euler",
                     "scheduler": "normal", "denoise": 1.0,
                     "model": ["4", 0], "positive": ["6", 0],
                     "negative": ["7", 0], "latent_image": ["5", 0]}},
    "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
    "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "ce", "images": ["8", 0]}},
}

WORKFLOW_MAP_DEFAULT = {
    "_nota": "IDs de nodo del workflow.json. prompt/seed son obligatorios.",
    "prompt": "6", "negativo": "7", "seed": "3", "width": "5", "height": "5",
}


# ---------------------------------------------------------------------------
# Ejemplos: plantillas
# ---------------------------------------------------------------------------
PLANTILLAS = {
    # --- comerciales ---
    "producto": {
        "nombre": "producto", "descripcion": "Lanzamiento o feature de un producto",
        "tomas": [
            {"prompt": "{producto} sobre superficie minimalista, fondo neutro, {estilo}"},
            {"prompt": "primer plano del detalle de {producto}, texturas y materiales, {estilo}"},
            {"prompt": "{producto} en contexto de uso real, escena lifestyle, {estilo}"},
        ],
        "titular": "{titular}", "cta": "{cta}",
    },
    "tip": {
        "nombre": "tip", "descripcion": "Consejo rápido y accionable",
        "tomas": [
            {"prompt": "escena que ilustra el tema '{tema}', ambiente {estilo}"},
            {"prompt": "detalle que refuerza la idea: {idea}, {estilo}"},
            {"prompt": "resultado de aplicar {idea}, sensación de logro, {estilo}"},
        ],
        "titular": "{titular}", "cta": "{cta}",
    },
    "testimonio": {
        "nombre": "testimonio", "descripcion": "Prueba social / cliente satisfecho",
        "tomas": [
            {"prompt": "persona satisfecha en entorno cotidiano, retrato cálido, {estilo}"},
            {"prompt": "momento de uso con expresión positiva, {estilo}"},
            {"prompt": "plano de cierre acogedor y aspiracional, {estilo}"},
        ],
        "titular": "{titular}", "cta": "{cta}",
    },
    # --- orgánicas (pilares) ---
    "dato": {
        "nombre": "dato", "descripcion": "Dato sorprendente (educar)",
        "tomas": [
            {"prompt": "imagen conceptual que representa '{tema}', estilo editorial, {estilo}"},
            {"prompt": "visual de un dato clave sobre {tema}, infografía limpia, {estilo}"},
            {"prompt": "cierre memorable sobre {tema}, {estilo}"},
        ],
        "titular": "{titular}", "cta": "{cta}",
    },
    "tutorial": {
        "nombre": "tutorial", "descripcion": "Paso a paso (educar)",
        "tomas": [
            {"prompt": "paso 1 de cómo {tema}, escena clara y didáctica, {estilo}"},
            {"prompt": "paso 2 de {tema}, detalle de la acción, {estilo}"},
            {"prompt": "resultado final de {tema}, antes y después, {estilo}"},
        ],
        "titular": "{titular}", "cta": "{cta}",
    },
    "mito": {
        "nombre": "mito", "descripcion": "Mito vs realidad (educar)",
        "tomas": [
            {"prompt": "representación del mito sobre {tema}, tono de duda, {estilo}"},
            {"prompt": "la realidad sobre {tema}, tono claro y seguro, {estilo}"},
            {"prompt": "conclusión que desmonta el mito de {tema}, {estilo}"},
        ],
        "titular": "{titular}", "cta": "{cta}",
    },
    "lista": {
        "nombre": "lista", "descripcion": "Lista enumerada (entretener)",
        "tomas": [
            {"prompt": "primer elemento de una lista sobre {tema}, gráfico dinámico, {estilo}"},
            {"prompt": "elemento intermedio sobre {tema}, ritmo visual, {estilo}"},
            {"prompt": "elemento final de la lista sobre {tema}, remate, {estilo}"},
        ],
        "titular": "{titular}", "cta": "{cta}",
    },
    "pov": {
        "nombre": "pov", "descripcion": "Punto de vista (entretener)",
        "tomas": [
            {"prompt": "escena en primera persona (POV) viviendo {tema}, inmersivo, {estilo}"},
            {"prompt": "momento de giro sobre {tema}, expresivo, {estilo}"},
            {"prompt": "desenlace satisfactorio de {tema}, {estilo}"},
        ],
        "titular": "{titular}", "cta": "{cta}",
    },
    "historia": {
        "nombre": "historia", "descripcion": "Relato emocional (inspirar)",
        "tomas": [
            {"prompt": "inicio de una historia sobre {tema}, atmósfera evocadora, {estilo}"},
            {"prompt": "punto de tensión de la historia de {tema}, emotivo, {estilo}"},
            {"prompt": "final inspirador sobre {tema}, luz cálida, {estilo}"},
        ],
        "titular": "{titular}", "cta": "{cta}",
    },
    "pregunta": {
        "nombre": "pregunta", "descripcion": "Pregunta a la comunidad (comunidad)",
        "tomas": [
            {"prompt": "imagen que invita a opinar sobre {tema}, abierta y cercana, {estilo}"},
            {"prompt": "dos opciones contrapuestas sobre {tema}, {estilo}"},
            {"prompt": "llamada a comentar sobre {tema}, ambiente de comunidad, {estilo}"},
        ],
        "titular": "{titular}", "cta": "{cta}",
    },
}


PILARES = {
    "pilares": {
        "educar": {
            "peso": 0.4, "plantillas": ["dato", "tutorial", "mito"],
            "cta": "Guarda este post",
            "hooks": ["Lo que nadie te cuenta de {tema}", "3 errores comunes con {tema}",
                      "La guía rápida de {tema}", "¿Lo estás haciendo bien con {tema}?"],
        },
        "entretener": {
            "peso": 0.3, "plantillas": ["lista", "pov"],
            "cta": "Comparte con quien lo necesite",
            "hooks": ["POV: por fin entiendes {tema}", "5 cosas de {tema} que no sabías",
                      "Cuando descubres {tema}"],
        },
        "inspirar": {
            "peso": 0.2, "plantillas": ["historia"],
            "cta": "Etiqueta a alguien",
            "hooks": ["De cero a dominar {tema}", "La historia detrás de {tema}",
                      "Por qué {tema} lo cambia todo"],
        },
        "comunidad": {
            "peso": 0.1, "plantillas": ["pregunta"],
            "cta": "Cuéntanoslo en comentarios",
            "hooks": ["¿Tu mayor duda con {tema}?", "¿Equipo {tema}, sí o no?",
                      "Necesitamos tu opinión sobre {tema}"],
        },
    }
}


# ---------------------------------------------------------------------------
# Ejemplos: plan e intención de arranque (dentro de la semana)
# ---------------------------------------------------------------------------
PLAN_EJEMPLO = {
    "config": {
        "formatos": ["9:16", "1:1"],
        "duracion_toma": 3.5, "fps": 30, "transicion": 0.5,
        "reintentos": 2,
        "hosts": ["127.0.0.1:8188"],
        "editores": 4,
    },
    "items": [
        {"template": "producto", "marca": "default",
         "vars": {"producto": "Zapatilla Aera", "titular": "Nueva Aera", "cta": "Compra ya"}},
        {"template": "tip", "marca": "default",
         "vars": {"tema": "running", "idea": "calienta 5 min",
                  "titular": "Tip runner", "cta": "Síguenos"}},
    ],
}

INTENCION_EJEMPLO = {
    "marca": "default",
    "total": 24,
    "canales": ["tiktok", "ig-feed", "youtube"],
    "temas": ["sentadilla correcta", "proteína", "descanso", "movilidad"],
    "mezcla": {"educar": 0.4, "entretener": 0.3, "inspirar": 0.2, "comunidad": 0.1},
}


# ---------------------------------------------------------------------------
def _write_if_missing(path, data):
    if os.path.exists(path):
        return False
    save_json(path, data)
    log(f"  + {os.path.relpath(path)}")
    return True


def sembrar_ejemplos():
    """Crea marca/plantillas/pilares de ejemplo si faltan. Idempotente."""
    creado = False
    md = os.path.join(MARCAS_DIR, "default")
    os.makedirs(md, exist_ok=True)
    creado |= _write_if_missing(os.path.join(md, "estilo.json"), ESTILO_DEFAULT)
    creado |= _write_if_missing(os.path.join(md, "workflow.json"), WORKFLOW_DEFAULT)
    creado |= _write_if_missing(os.path.join(md, "workflow.map.json"), WORKFLOW_MAP_DEFAULT)

    os.makedirs(PLANTILLAS_DIR, exist_ok=True)
    for nombre, data in PLANTILLAS.items():
        creado |= _write_if_missing(os.path.join(PLANTILLAS_DIR, f"{nombre}.json"), data)

    creado |= _write_if_missing(PILARES_FILE, PILARES)
    if creado:
        log("[new_week] ejemplos del proyecto creados.")


def crear_semana(semana):
    p = paths_semana(semana)
    for d in (p["base"], p["inputs_audio"], p["generated"], p["edited"]):
        os.makedirs(d, exist_ok=True)
    log(f"[new_week] semana {semana} en {os.path.relpath(p['base'])}")
    _write_if_missing(p["plan"], PLAN_EJEMPLO)
    _write_if_missing(p["intencion"], INTENCION_EJEMPLO)


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Uso: python3 new_week.py <SEMANA>   (p.ej. 2026-W23)")
    sembrar_ejemplos()
    crear_semana(sys.argv[1])
    log("\nSiguiente paso:\n"
        "  1) Edita semanas/%s/plan.json (o usa plan_organico.py con intencion.json)\n"
        "  2) python3 engine/pipeline.py %s --simular   # prueba sin GPU"
        % (sys.argv[1], sys.argv[1]))


if __name__ == "__main__":
    main()
