#!/usr/bin/env python3
"""
comfy.py — Cliente mínimo de ComfyUI con SOLO librería estándar.

A diferencia del comfy_batch.py de la raíz (que usa requests + websocket), aquí
todo va con urllib y se sondea /history en vez de escuchar el WebSocket, para no
depender de pip. La generación de una imagen SDXL es corta, así que el polling
es perfectamente válido.

Funciones públicas:
  - ping(host)                      -> bool (¿responde /system_stats?)
  - inject(workflow, mapa, prompt, negativo, seed, width, height) -> workflow
  - generar_imagen(host, workflow, dest, ...) -> ruta del PNG descargado

Un "host" es "ip:puerto" (p.ej. "127.0.0.1:8188"). Se asume http.
"""

import copy
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


def _url(host, path):
    host = host.strip()
    if not host.startswith("http://") and not host.startswith("https://"):
        host = "http://" + host
    return host.rstrip("/") + path


def _get(host, path, timeout=30):
    with urllib.request.urlopen(_url(host, path), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _post(host, path, payload, timeout=60):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        _url(host, path), data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def ping(host, timeout=10):
    """True si ComfyUI responde en ese host."""
    try:
        _get(host, "/system_stats", timeout=timeout)
        return True
    except Exception:
        return False


def wait_ready(host, timeout=600, interval=5):
    """Espera a que ComfyUI cargue (los modelos grandes tardan)."""
    start = time.time()
    while time.time() - start < timeout:
        if ping(host):
            return True
        time.sleep(interval)
    raise TimeoutError(f"ComfyUI no respondió en {timeout}s ({host})")


# ---------------------------------------------------------------------------
# Inyección de parámetros en el workflow
# ---------------------------------------------------------------------------
def _set_text(node, text):
    inputs = node.setdefault("inputs", {})
    if "text" in inputs:
        inputs["text"] = text
        return True
    for k, v in inputs.items():
        if isinstance(v, str):
            inputs[k] = text
            return True
    inputs["text"] = text
    return True


def _heuristic_nodes(workflow):
    """Respaldo si el mapa no trae IDs: localiza prompt+/prompt-/seed por clase."""
    pos = neg = seed = None
    sampler = None
    for nid, node in workflow.items():
        ct = node.get("class_type", "")
        if "Sampler" in ct or "KSampler" in ct:
            sampler = nid
    if sampler:
        ins = workflow[sampler].get("inputs", {})
        lp, ln = ins.get("positive"), ins.get("negative")
        if isinstance(lp, list) and lp:
            pos = str(lp[0])
        if isinstance(ln, list) and ln:
            neg = str(ln[0])
        seed = sampler
    if pos is None:
        for nid, node in workflow.items():
            if "TextEncode" in node.get("class_type", ""):
                pos = nid
                break
    return pos, neg, seed


def inject(base_workflow, mapa, prompt, negativo=None, seed=None,
           width=None, height=None):
    """
    Copia el workflow base e inyecta prompt/negativo/seed/resolución usando el
    mapa de IDs de nodo (marcas/<m>/workflow.map.json). Si el mapa no trae algún
    ID, recurre a heurísticas por clase de nodo.

    mapa: {"prompt": "6", "negativo": "7", "seed": "3",
           "width": "5", "height": "5"}  (negativo/width/height opcionales)
    """
    wf = copy.deepcopy(base_workflow)
    # Quita claves auxiliares que no sean nodos (p.ej. notas).
    wf = {k: v for k, v in wf.items() if isinstance(v, dict) and "class_type" in v}

    mapa = mapa or {}
    pos_id = str(mapa.get("prompt")) if mapa.get("prompt") is not None else None
    neg_id = str(mapa.get("negativo")) if mapa.get("negativo") is not None else None
    seed_id = str(mapa.get("seed")) if mapa.get("seed") is not None else None
    w_id = str(mapa.get("width")) if mapa.get("width") is not None else None
    h_id = str(mapa.get("height")) if mapa.get("height") is not None else None

    if pos_id is None or seed_id is None:
        h_pos, h_neg, h_seed = _heuristic_nodes(wf)
        pos_id = pos_id or h_pos
        neg_id = neg_id or h_neg
        seed_id = seed_id or h_seed

    if pos_id is None or pos_id not in wf:
        raise RuntimeError("No localicé el nodo de prompt; revisa workflow.map.json")
    _set_text(wf[pos_id], prompt)

    if negativo and neg_id and neg_id in wf:
        _set_text(wf[neg_id], negativo)

    if seed is not None and seed_id and seed_id in wf:
        ins = wf[seed_id].setdefault("inputs", {})
        for k in ("seed", "noise_seed"):
            if k in ins:
                ins[k] = int(seed)
                break
        else:
            ins["seed"] = int(seed)

    if width is not None and w_id and w_id in wf:
        wf[w_id].setdefault("inputs", {})["width"] = int(width)
    if height is not None and h_id and h_id in wf:
        wf[h_id].setdefault("inputs", {})["height"] = int(height)

    return wf


# ---------------------------------------------------------------------------
# Generación de una imagen
# ---------------------------------------------------------------------------
def _download(host, item, dest):
    params = urllib.parse.urlencode({
        "filename": item.get("filename", ""),
        "subfolder": item.get("subfolder", ""),
        "type": item.get("type", "output"),
    })
    url = _url(host, "/view?" + params)
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as r, open(dest, "wb") as f:
        f.write(r.read())
    return dest


def generar_imagen(host, workflow, dest, gen_timeout=600, poll=2):
    """
    Encola un workflow ya inyectado, espera a que termine sondeando /history y
    descarga la primera imagen de salida a `dest`. Devuelve la ruta.
    """
    client_id = str(uuid.uuid4())
    res = _post(host, "/prompt", {"prompt": workflow, "client_id": client_id})
    prompt_id = res.get("prompt_id")
    if not prompt_id:
        raise RuntimeError(f"ComfyUI no devolvió prompt_id: {res}")

    start = time.time()
    while True:
        if time.time() - start > gen_timeout:
            raise TimeoutError(f"Timeout ({gen_timeout}s) generando {prompt_id}")
        try:
            hist = _get(host, f"/history/{prompt_id}", timeout=30)
        except urllib.error.URLError:
            time.sleep(poll)
            continue
        entry = hist.get(prompt_id)
        if entry:
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                raise RuntimeError(f"ComfyUI reportó error en {prompt_id}")
            outputs = entry.get("outputs", {})
            for node_out in outputs.values():
                for key in ("images", "gifs", "videos"):
                    for it in node_out.get(key, []):
                        if it.get("filename"):
                            return _download(host, it, dest)
            # Terminó (hay entry) pero sin imágenes -> error claro.
            if status.get("completed"):
                raise RuntimeError(f"{prompt_id} terminó sin imágenes de salida")
        time.sleep(poll)
