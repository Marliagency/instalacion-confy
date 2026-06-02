#!/usr/bin/env python3
"""
formats.py — Registro de motores ComfyUI y carga/inyección de workflows.

Los workflows viven YA VALIDADOS en workflows/api/*.json (formato API) con un
mapa `_meta.inject` que dice, por cada parámetro, en qué nodo/input escribirlo.
Así no se reconstruye el grafo nunca: solo se cargan e inyectan valores.
"""
import json

# motor -> plantilla de workflow (formato API). slideshow_ffmpeg no usa ComfyUI.
ENGINE_WORKFLOW = {
    "wan_i2v":     "workflows/api/wan_i2v.json",
    "wan_lipsync": "workflows/api/wan_lipsync.json",
}

# resolución de generación WAN por aspecto (múltiplos de 16)
ASPECT_WAN_WH = {
    "9:16": (480, 832), "4:5": (512, 640),
    "1:1": (512, 512), "16:9": (832, 480),
}


def load_template(engine):
    """Devuelve (graph, inject_map). Lanza si la plantilla está sin validar."""
    path = ENGINE_WORKFLOW.get(engine)
    if not path:
        raise ValueError(f"Motor sin workflow ComfyUI: {engine}")
    data = json.load(open(path))
    meta = data.get("_meta", {})
    if meta.get("pendiente_validar"):
        raise RuntimeError(
            f"El workflow '{engine}' ({path}) está PENDIENTE DE VALIDAR en el pod. "
            "Arranca un pod, introspecciona /object_info y completa el grafo + "
            "el mapa _meta.inject antes de usarlo (ver SESION_B.md)."
        )
    inject = meta.get("inject", {})
    graph = {k: v for k, v in data.items() if k != "_meta"}
    return graph, inject


def inject(graph, inject_map, params):
    """Aplica params sobre el grafo según el mapa de inyección. Copia profunda."""
    g = json.loads(json.dumps(graph))
    for key, value in params.items():
        for node_id, field in inject_map.get(key, []):
            if node_id in g:
                g[node_id]["inputs"][field] = value
    return g
