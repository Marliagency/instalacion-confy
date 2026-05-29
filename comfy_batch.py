#!/usr/bin/env python3
"""
comfy_batch.py — Puente entre Claude Code y ComfyUI (en un pod de RunPod).

Lee un JSON de prompts (imágenes y/o videos), inyecta cada uno en el workflow
correspondiente, los encola en la API de ComfyUI, espera a que terminen
(escuchando el WebSocket), y descarga los archivos resultantes a una carpeta
local. Genera un reporte del lote en JSON.

Uso típico (lo lanza Claude Code por ti):

    python3 comfy_batch.py \
        --comfy-url https://XXXX-8188.proxy.runpod.net \
        --prompts ./batch_prompts.json \
        --out ./outputs \
        --workflow-video ./workflows/wan_t2v.json \
        --workflow-image ./workflows/sdxl_t2i.json

Validar localmente SIN GPU (no contacta ComfyUI, solo comprueba que los
workflows y la inyección funcionan):

    python3 comfy_batch.py --dry-run \
        --prompts ./batch_prompts.example.json \
        --workflow-image ./workflows/sdxl_t2i.json

Requisitos:
    pip3 install requests websocket-client

FORMATO DE CADA PROMPT (en el JSON del lote):
    {
      "id": "v01",                 # identificador del archivo de salida
      "prompt": "...",             # prompt positivo (obligatorio)
      "tipo": "video",             # "video" o "imagen" (por defecto "video")
      "negativo": "...",           # opcional, prompt negativo
      "formato": "9:16",           # informativo
      "width": 832,                # opcional, sobrescribe la resolución del workflow
      "height": 1216,              # opcional
      "frames": 81,                # opcional (solo video), nº de fotogramas
      "seed": 12345                # opcional; si falta, se genera una aleatoria
    }

SOBRE LOS WORKFLOWS:
    ComfyUI no genera desde texto plano: necesita un "workflow" (grafo de nodos)
    en formato API. Exporta el tuyo una vez desde la UI de ComfyUI
    (engranaje -> Enable Dev mode Options -> botón "Save (API Format)").
    Este script localiza automáticamente, dentro del workflow:
      - el nodo de prompt POSITIVO y NEGATIVO (siguiendo los enlaces del KSampler,
        con respaldo por título/clase),
      - los nodos de semilla, resolución y nº de fotogramas,
    e inyecta los valores de cada item del lote. Si tu workflow tiene una
    estructura inusual, ajusta las heurísticas de abajo.
"""

import argparse
import json
import os
import random
import time
import uuid
import urllib.request
import urllib.parse

try:
    import requests
    import websocket  # websocket-client
except ImportError as e:  # pragma: no cover
    raise SystemExit(
        "Faltan dependencias. Instala con: pip3 install requests websocket-client\n"
        f"Detalle: {e}"
    )


# ---------------------------------------------------------------------------
# Utilidades de carga
# ---------------------------------------------------------------------------
def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Detección de nodos dentro del workflow
# ---------------------------------------------------------------------------
def _iter_nodes(workflow):
    """Itera (id, nodo) saltando claves auxiliares (p.ej. '_NOTA') que no son nodos."""
    for node_id, node in workflow.items():
        if isinstance(node, dict) and "class_type" in node:
            yield node_id, node


def _find_sampler_node(workflow):
    """Devuelve el id del primer nodo tipo sampler (KSampler, WanSampler, etc.)."""
    for node_id, node in _iter_nodes(workflow):
        ctype = node.get("class_type", "")
        if "Sampler" in ctype or "KSampler" in ctype:
            return node_id
    return None


def find_prompt_nodes(workflow):
    """
    Localiza los nodos de prompt POSITIVO y NEGATIVO.

    Estrategia (de más fiable a menos):
      1) Sigue los enlaces 'positive' / 'negative' del nodo sampler.
      2) Usa el título del nodo (_meta.title) que contenga 'positive'/'negative'.
      3) Cae al primer / segundo nodo de tipo *TextEncode*.

    Devuelve (id_positivo, id_negativo_or_None).
    """
    pos_id = neg_id = None

    sampler = _find_sampler_node(workflow)
    if sampler is not None:
        inputs = workflow[sampler].get("inputs", {})
        link_pos = inputs.get("positive")
        link_neg = inputs.get("negative")
        if isinstance(link_pos, list) and link_pos:
            pos_id = str(link_pos[0])
        if isinstance(link_neg, list) and link_neg:
            neg_id = str(link_neg[0])

    # Verifica/rellena por título y clase
    text_nodes = []
    for node_id, node in _iter_nodes(workflow):
        ctype = node.get("class_type", "")
        if "TextEncode" in ctype or "Prompt" in ctype or "CLIPTextEncode" in ctype:
            text_nodes.append(node_id)

    if pos_id is None or neg_id is None:
        for node_id in text_nodes:
            title = (workflow[node_id].get("_meta", {}).get("title") or "").lower()
            if pos_id is None and ("positive" in title or title.strip() in ("pos", "prompt")):
                pos_id = node_id
            if neg_id is None and ("negative" in title or title.strip() in ("neg",)):
                neg_id = node_id

    if pos_id is None and text_nodes:
        pos_id = text_nodes[0]
    if neg_id is None and len(text_nodes) > 1:
        # el negativo es el otro nodo de texto distinto del positivo
        for node_id in text_nodes:
            if node_id != pos_id:
                neg_id = node_id
                break

    if pos_id is None:
        raise RuntimeError(
            "No encontré un nodo de prompt de texto en el workflow. "
            "Revisa el JSON del workflow y ajusta find_prompt_nodes()."
        )
    return pos_id, neg_id


def _set_text(node, text):
    """Pone el texto en el campo de texto del nodo (normalmente 'text')."""
    inputs = node.get("inputs", {})
    if "text" in inputs:
        inputs["text"] = text
        return True
    for k, v in inputs.items():
        if isinstance(v, str):
            inputs[k] = text
            return True
    return False


# ---------------------------------------------------------------------------
# Inyección de parámetros
# ---------------------------------------------------------------------------
SEED_KEYS = ("seed", "noise_seed")
FRAME_KEYS = ("length", "num_frames", "frames", "video_frames", "frame_count")


def build_workflow(base_workflow, item):
    """Copia el workflow base e inyecta los parámetros del item del lote."""
    wf = json.loads(json.dumps(base_workflow))  # copia profunda
    # Elimina claves auxiliares de nivel raíz (p.ej. '_NOTA') que no son nodos,
    # para no enviarlas a la API de ComfyUI.
    wf = {k: v for k, v in wf.items() if isinstance(v, dict) and "class_type" in v}
    pos_id, neg_id = find_prompt_nodes(wf)

    # Prompt positivo
    _set_text(wf[pos_id], item["prompt"])

    # Prompt negativo (si hay nodo y el item lo trae)
    negativo = item.get("negativo")
    if neg_id is not None and negativo:
        _set_text(wf[neg_id], negativo)

    # Semilla: si el item no trae una, generamos aleatoria para que cada
    # variación sea distinta aunque el prompt coincida.
    seed = item.get("seed")
    if seed is None:
        seed = random.randint(0, 2_147_483_646)
    for _id, node in _iter_nodes(wf):
        inputs = node.get("inputs", {})
        for k in SEED_KEYS:
            if k in inputs and isinstance(inputs[k], (int, float)):
                inputs[k] = int(seed)

    # Resolución (si el item la trae)
    width = item.get("width")
    height = item.get("height")
    for _id, node in _iter_nodes(wf):
        inputs = node.get("inputs", {})
        if width is not None and "width" in inputs and isinstance(inputs["width"], (int, float)):
            inputs["width"] = int(width)
        if height is not None and "height" in inputs and isinstance(inputs["height"], (int, float)):
            inputs["height"] = int(height)

    # Nº de fotogramas (solo videos, si el item lo trae)
    frames = item.get("frames")
    if frames is not None:
        for _id, node in _iter_nodes(wf):
            inputs = node.get("inputs", {})
            for k in FRAME_KEYS:
                if k in inputs and isinstance(inputs[k], (int, float)):
                    inputs[k] = int(frames)

    return wf, pos_id, neg_id, int(seed)


# ---------------------------------------------------------------------------
# Comunicación con ComfyUI
# ---------------------------------------------------------------------------
def wait_for_comfy_ready(comfy_url, timeout=600, interval=5):
    """Sondea ComfyUI hasta que responde (los modelos grandes tardan en cargar)."""
    start = time.time()
    last_err = None
    while time.time() - start < timeout:
        try:
            r = requests.get(f"{comfy_url}/system_stats", timeout=10)
            if r.status_code == 200:
                return True
        except Exception as e:  # noqa: BLE001
            last_err = e
        time.sleep(interval)
    raise TimeoutError(
        f"ComfyUI no respondió en {timeout}s ({comfy_url}). Último error: {last_err}"
    )


def queue_prompt(comfy_url, workflow, client_id, retries=3):
    """Encola un prompt en ComfyUI. Devuelve el prompt_id."""
    payload = {"prompt": workflow, "client_id": client_id}
    last_err = None
    for attempt in range(retries):
        try:
            r = requests.post(f"{comfy_url}/prompt", json=payload, timeout=30)
            r.raise_for_status()
            return r.json()["prompt_id"]
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"No pude encolar el prompt: {last_err}")


def wait_for_completion(comfy_url, prompt_id, client_id, timeout=3600):
    """
    Espera a que termine la generación escuchando el WebSocket de ComfyUI.
    Devuelve cuando el prompt_id ya no se está ejecutando. Lanza excepción si
    ComfyUI reporta un error de ejecución para este prompt.
    """
    ws_url = comfy_url.replace("https://", "wss://").replace("http://", "ws://")
    ws = websocket.create_connection(f"{ws_url}/ws?clientId={client_id}", timeout=60)
    start = time.time()
    try:
        while True:
            if time.time() - start > timeout:
                raise TimeoutError(f"Timeout esperando prompt {prompt_id}")
            msg = ws.recv()
            if not isinstance(msg, str):
                continue
            data = json.loads(msg)
            mtype = data.get("type")
            d = data.get("data", {})
            if mtype == "executing":
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
    for node_out in outputs.values():
        # Según el nodo de guardado, los archivos vienen bajo estas claves
        for key in ("gifs", "videos", "images"):
            for item in node_out.get(key, []):
                fname = item.get("filename")
                if not fname:
                    continue
                params = urllib.parse.urlencode({
                    "filename": fname,
                    "subfolder": item.get("subfolder", ""),
                    "type": item.get("type", "output"),
                })
                url = f"{comfy_url}/view?{params}"
                local_name = f"{vid_id}_{fname}" if not fname.startswith(vid_id) else fname
                local_path = os.path.join(out_dir, local_name)
                urllib.request.urlretrieve(url, local_path)
                saved.append(local_path)
    return saved


# ---------------------------------------------------------------------------
# Selección de workflow por tipo
# ---------------------------------------------------------------------------
def pick_workflow(item, workflows):
    """Elige el workflow según el 'tipo' del item ('video' o 'imagen')."""
    tipo = (item.get("tipo") or "video").lower()
    if tipo in ("imagen", "image", "img", "foto"):
        wf = workflows.get("imagen")
        kind = "imagen"
    else:
        wf = workflows.get("video")
        kind = "video"
    if wf is None:
        # Respaldo: usa el único workflow disponible
        wf = workflows.get("video") or workflows.get("imagen")
    if wf is None:
        raise RuntimeError(
            f"No hay workflow cargado para tipo '{tipo}'. "
            "Pasa --workflow-video y/o --workflow-image (o --workflow)."
        )
    return wf, kind


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Lote de generación ComfyUI (imágenes y videos).")
    ap.add_argument("--comfy-url", help="URL pública de ComfyUI (puerto 8188)")
    ap.add_argument("--prompts", required=True, help="JSON con la lista de prompts del lote")
    ap.add_argument("--out", default="./outputs", help="Carpeta local de salida")
    ap.add_argument("--workflow-video", help="Workflow ComfyUI (formato API) para videos")
    ap.add_argument("--workflow-image", help="Workflow ComfyUI (formato API) para imágenes")
    ap.add_argument("--workflow", help="Workflow único (se usa para ambos tipos si no especificas los de arriba)")
    ap.add_argument("--ready-timeout", type=int, default=600, help="Segundos a esperar a que ComfyUI cargue")
    ap.add_argument("--gen-timeout", type=int, default=3600, help="Segundos máx. por generación")
    ap.add_argument("--dry-run", action="store_true", help="Valida workflows e inyección sin contactar ComfyUI")
    args = ap.parse_args()

    # Carga de workflows
    workflows = {}
    if args.workflow_video:
        workflows["video"] = load_json(args.workflow_video)
    if args.workflow_image:
        workflows["imagen"] = load_json(args.workflow_image)
    if args.workflow:
        single = load_json(args.workflow)
        workflows.setdefault("video", single)
        workflows.setdefault("imagen", single)
    if not workflows:
        raise SystemExit("Debes pasar --workflow-video, --workflow-image o --workflow.")

    prompts = load_json(args.prompts)
    if not isinstance(prompts, list) or not prompts:
        raise SystemExit("El JSON de prompts debe ser una lista no vacía.")

    # ---- DRY RUN: solo valida, no genera ----
    if args.dry_run:
        print(f"[dry-run] {len(prompts)} items. Validando inyección...\n")
        ok = 0
        for i, item in enumerate(prompts, 1):
            vid_id = item.get("id", f"v{i:02d}")
            try:
                base, kind = pick_workflow(item, workflows)
                wf, pos_id, neg_id, seed = build_workflow(base, item)
                texto = wf[pos_id]["inputs"].get("text", "")
                print(f"[{i}/{len(prompts)}] {vid_id} ({kind}) -> nodo pos={pos_id} neg={neg_id} seed={seed}")
                print(f"        prompt inyectado: {texto[:80]}{'...' if len(texto) > 80 else ''}")
                ok += 1
            except Exception as e:  # noqa: BLE001
                print(f"[{i}/{len(prompts)}] {vid_id}  ERROR: {e}")
        print(f"\n[dry-run] OK: {ok}/{len(prompts)} items validados.")
        return

    # ---- EJECUCIÓN REAL ----
    if not args.comfy_url:
        raise SystemExit("Falta --comfy-url para la ejecución real (o usa --dry-run).")

    os.makedirs(args.out, exist_ok=True)
    comfy_url = args.comfy_url.rstrip("/")
    client_id = str(uuid.uuid4())

    print(f"[i] ComfyUI: {comfy_url}")
    print(f"[i] Esperando a que ComfyUI esté listo (máx {args.ready_timeout}s)...")
    wait_for_comfy_ready(comfy_url, timeout=args.ready_timeout)
    print(f"[i] ComfyUI listo. {len(prompts)} items en el lote.\n")

    report = {"ok": [], "fail": []}
    t0 = time.time()

    for i, item in enumerate(prompts, 1):
        vid_id = item.get("id", f"v{i:02d}")
        try:
            base, kind = pick_workflow(item, workflows)
            wf, _pos, _neg, seed = build_workflow(base, item)
            print(f"[{i}/{len(prompts)}] {vid_id} ({kind}, seed={seed}): encolando...")
            pid = queue_prompt(comfy_url, wf, client_id)
            wait_for_completion(comfy_url, pid, client_id, timeout=args.gen_timeout)
            saved = download_outputs(comfy_url, pid, args.out, vid_id)
            if saved:
                print(f"      OK -> {', '.join(os.path.basename(s) for s in saved)}")
                report["ok"].append(vid_id)
            else:
                print("      AVISO: terminó sin archivos de salida")
                report["fail"].append({"id": vid_id, "error": "sin salida"})
        except Exception as e:  # noqa: BLE001
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

    with open(os.path.join(args.out, "_reporte_lote.json"), "w", encoding="utf-8") as f:
        json.dump({"resumen": report, "minutos": dt / 60}, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
