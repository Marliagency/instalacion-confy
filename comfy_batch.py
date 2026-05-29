#!/usr/bin/env python3
"""
comfy_batch.py — Puente entre Claude Code y ComfyUI (en un pod de RunPod).

Lee un JSON de prompts, los envía uno a uno a la API de ComfyUI vía el endpoint
/prompt, espera a que cada generación termine (escuchando el WebSocket de
ComfyUI), y descarga los videos resultantes a una carpeta local.

Uso:
    python3 comfy_batch.py \
        --comfy-url https://XXXX-8188.proxy.runpod.net \
        --prompts ./batch_prompts.json \
        --out ./outputs \
        --workflow ./wan_workflow.json

Requisitos:
    pip3 install requests websocket-client

IMPORTANTE sobre --workflow:
    ComfyUI no genera desde texto plano: necesita un "workflow" (grafo de nodos)
    en formato API. Debes exportar UNA vez tu workflow WAN desde la UI de ComfyUI
    (menú: guardar/exportar en formato API) y guardarlo como wan_workflow.json.
    Este script localiza dentro de ese workflow el nodo de texto (el prompt
    positivo) y le inyecta cada prompt del lote. Ajusta POSITIVE_NODE_TITLE /
    detección abajo si tu workflow usa otra estructura.
"""

import argparse
import json
import os
import time
import uuid
import urllib.request
import urllib.parse

import requests
import websocket  # websocket-client


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_positive_prompt_node(workflow):
    """
    Heurística para localizar el nodo donde va el prompt de texto positivo.
    Busca un nodo con class_type tipo CLIPTextEncode (o similar) cuyo título
    o meta sugiera 'positive'. Devuelve la clave del nodo.
    Ajusta esto a tu workflow concreto si hace falta.
    """
    candidates = []
    for node_id, node in workflow.items():
        ctype = node.get("class_type", "")
        if "CLIPTextEncode" in ctype or "TextEncode" in ctype or "Prompt" in ctype:
            candidates.append(node_id)
    # Preferir el que tenga 'positive' en el título si existe
    for node_id in candidates:
        meta = workflow[node_id].get("_meta", {})
        title = (meta.get("title") or "").lower()
        if "positive" in title or "pos" in title:
            return node_id
    # Si no, el primer candidato
    if candidates:
        return candidates[0]
    raise RuntimeError(
        "No encontré un nodo de prompt de texto en el workflow. "
        "Revisa wan_workflow.json y ajusta find_positive_prompt_node()."
    )


def inject_prompt(workflow, node_id, text):
    """Inyecta el texto del prompt en el nodo de texto positivo."""
    wf = json.loads(json.dumps(workflow))  # copia profunda
    # El campo de texto suele llamarse 'text' dentro de inputs
    if "inputs" in wf[node_id] and "text" in wf[node_id]["inputs"]:
        wf[node_id]["inputs"]["text"] = text
    else:
        # fallback: intenta el primer input string
        for k, v in wf[node_id].get("inputs", {}).items():
            if isinstance(v, str):
                wf[node_id]["inputs"][k] = text
                break
    return wf


def queue_prompt(comfy_url, workflow, client_id):
    """Encola un prompt en ComfyUI. Devuelve el prompt_id."""
    payload = {"prompt": workflow, "client_id": client_id}
    r = requests.post(f"{comfy_url}/prompt", json=payload, timeout=30)
    r.raise_for_status()
    return r.json()["prompt_id"]


def wait_for_completion(comfy_url, prompt_id, client_id, timeout=1800):
    """
    Espera a que termine la generación escuchando el WebSocket de ComfyUI.
    Devuelve cuando el prompt_id ya no está ejecutándose. Lanza una excepción
    si ComfyUI reporta un error de ejecución para este prompt.
    """
    ws_url = comfy_url.replace("https://", "wss://").replace("http://", "ws://")
    ws = websocket.create_connection(f"{ws_url}/ws?clientId={client_id}", timeout=60)
    start = time.time()
    try:
        while True:
            if time.time() - start > timeout:
                raise TimeoutError(f"Timeout esperando prompt {prompt_id}")
            msg = ws.recv()
            if isinstance(msg, str):
                data = json.loads(msg)
                mtype = data.get("type")
                d = data.get("data", {})
                if mtype == "executing":
                    # node == None y prompt_id coincide => terminó
                    if d.get("node") is None and d.get("prompt_id") == prompt_id:
                        return
                elif mtype == "execution_error" and d.get("prompt_id") == prompt_id:
                    raise RuntimeError(
                        d.get("exception_message", "error de ejecución en ComfyUI")
                    )
    finally:
        ws.close()


def get_history(comfy_url, prompt_id):
    r = requests.get(f"{comfy_url}/history/{prompt_id}", timeout=30)
    r.raise_for_status()
    return r.json()


def download_outputs(comfy_url, prompt_id, out_dir, vid_id):
    """Descarga los archivos de salida (videos/imágenes) de un prompt."""
    hist = get_history(comfy_url, prompt_id)
    entry = hist.get(prompt_id, {})
    outputs = entry.get("outputs", {})
    saved = []
    for node_id, node_out in outputs.items():
        # Los videos pueden venir bajo 'gifs', 'videos', o 'images' según el nodo
        for key in ("gifs", "videos", "images"):
            for item in node_out.get(key, []):
                fname = item.get("filename")
                subfolder = item.get("subfolder", "")
                ftype = item.get("type", "output")
                if not fname:
                    continue
                params = urllib.parse.urlencode(
                    {"filename": fname, "subfolder": subfolder, "type": ftype}
                )
                url = f"{comfy_url}/view?{params}"
                ext = os.path.splitext(fname)[1] or ".mp4"
                local_name = f"{vid_id}_{fname}" if not fname.startswith(vid_id) else fname
                local_path = os.path.join(out_dir, local_name)
                urllib.request.urlretrieve(url, local_path)
                saved.append(local_path)
    return saved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--comfy-url", required=True, help="URL pública de ComfyUI (puerto 8188)")
    ap.add_argument("--prompts", required=True, help="JSON con la lista de prompts del lote")
    ap.add_argument("--out", default="./outputs", help="Carpeta local de salida")
    ap.add_argument("--workflow", default="./wan_workflow.json", help="Workflow ComfyUI en formato API")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    comfy_url = args.comfy_url.rstrip("/")
    prompts = load_json(args.prompts)
    base_workflow = load_json(args.workflow)
    pos_node = find_positive_prompt_node(base_workflow)
    client_id = str(uuid.uuid4())

    print(f"[i] ComfyUI: {comfy_url}")
    print(f"[i] Nodo de prompt detectado: {pos_node}")
    print(f"[i] {len(prompts)} videos en el lote\n")

    report = {"ok": [], "fail": []}
    t0 = time.time()

    for i, item in enumerate(prompts, 1):
        vid_id = item.get("id", f"v{i:02d}")
        text = item["prompt"]
        print(f"[{i}/{len(prompts)}] {vid_id}: encolando...")
        try:
            wf = inject_prompt(base_workflow, pos_node, text)
            pid = queue_prompt(comfy_url, wf, client_id)
            wait_for_completion(comfy_url, pid, client_id)
            saved = download_outputs(comfy_url, pid, args.out, vid_id)
            if saved:
                print(f"      OK descargado: {', '.join(os.path.basename(s) for s in saved)}")
                report["ok"].append(vid_id)
            else:
                print(f"      AVISO terminó sin archivos de salida")
                report["fail"].append({"id": vid_id, "error": "sin salida"})
        except Exception as e:
            print(f"      ERROR: {e}")
            report["fail"].append({"id": vid_id, "error": str(e)})

    dt = time.time() - t0
    print("\n===== REPORTE DEL LOTE =====")
    print(f"OK:      {len(report['ok'])}")
    print(f"Fallos:  {len(report['fail'])}")
    print(f"Tiempo:  {dt/60:.1f} min de generación")
    print(f"Salida:  {os.path.abspath(args.out)}")
    if report["fail"]:
        print("Detalle de fallos:")
        for f in report["fail"]:
            print(f"  - {f['id']}: {f['error']}")
    # Guarda el reporte en JSON para que Claude Code lo lea
    with open(os.path.join(args.out, "_reporte_lote.json"), "w", encoding="utf-8") as f:
        json.dump({"resumen": report, "minutos": dt / 60}, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
