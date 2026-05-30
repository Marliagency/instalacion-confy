#!/usr/bin/env python3
"""Orquestador H200 (US-NC-1, pod desechable sin network volume).
Espera ComfyUI (modelos descargándose), verifica/ajusta los nombres reales de
los ficheros WAN en el workflow, genera el lote, y APAGA + BORRA el pod siempre.
"""
import os, sys, json, time, subprocess, requests

POD = os.environ.get("POD_ID", "mp6yz26pcq03qm")
URL = f"https://{POD}-8188.proxy.runpod.net"
BASE = "https://rest.runpod.io/v1"
H = {"Authorization": f"Bearer {os.environ['RUNPOD_API_KEY']}", "Content-Type": "application/json"}
WF = "/home/user/instalacion-confy/workflows/wan_t2v.json"

def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)

def wait_comfy(timeout=2400):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            r = requests.get(f"{URL}/system_stats", timeout=10)
            if r.status_code == 200:
                log(f"ComfyUI LISTO en {URL}")
                return True
            last = f"HTTP {r.status_code}"
        except Exception as e:
            last = str(e)[:60]
        log(f"  esperando ComfyUI (modelos descargando)... {last}")
        time.sleep(15)
    return False

def get_options(node):
    try:
        r = requests.get(f"{URL}/object_info/{node}", timeout=30)
        d = r.json()
        req = d[node]["input"]["required"]
        # primer campo cuya opción sea lista de ficheros
        for k, v in req.items():
            if isinstance(v, list) and v and isinstance(v[0], list):
                return k, v[0]
    except Exception as e:
        log(f"  object_info {node} err: {e}")
    return None, []

def pick(cands, want_substrings):
    for s in want_substrings:
        for c in cands:
            if s.lower() in c.lower():
                return c
    return cands[0] if cands else None

def fix_workflow():
    """Ajusta los nombres de fichero del workflow a lo que existe en el pod."""
    wf = json.load(open(WF))
    # UNET
    _, unets = get_options("UNETLoader")
    _, clips = get_options("CLIPLoader")
    _, vaes  = get_options("VAELoader")
    log(f"  UNET disp: {unets}")
    log(f"  CLIP disp: {clips}")
    log(f"  VAE  disp: {vaes}")
    changed = False
    for nid, node in wf.items():
        ct = node.get("class_type")
        if ct == "UNETLoader" and unets:
            sel = pick(unets, ["t2v", "wan2.1", "wan"])
            if sel: node["inputs"]["unet_name"] = sel; changed = True; log(f"  UNET -> {sel}")
        elif ct == "CLIPLoader" and clips:
            sel = pick(clips, ["umt5", "t5"])
            if sel: node["inputs"]["clip_name"] = sel; changed = True; log(f"  CLIP -> {sel}")
        elif ct == "VAELoader" and vaes:
            sel = pick(vaes, ["wan", "vae"])
            if sel: node["inputs"]["vae_name"] = sel; changed = True; log(f"  VAE  -> {sel}")
    if changed:
        json.dump(wf, open(WF, "w"), indent=2)
        log("  workflow actualizado con nombres reales.")

def stop_delete():
    try:
        r = requests.post(f"{BASE}/pods/{POD}/stop", headers=H, timeout=40)
        log(f"  STOP -> HTTP {r.status_code}")
    except Exception as e:
        log(f"  STOP err: {e}")
    time.sleep(3)
    try:
        r = requests.delete(f"{BASE}/pods/{POD}", headers=H, timeout=40)
        log(f"  DELETE -> HTTP {r.status_code}")
    except Exception as e:
        log(f"  DELETE err: {e}")

def main():
    log(f"Orquestador H200 {POD} ({URL})")
    try:
        if not wait_comfy():
            log("ComfyUI no respondió a tiempo. Abortando.")
            return
        # Margen extra: tras /system_stats OK los modelos pueden seguir copiándose
        time.sleep(20)
        fix_workflow()
        log("Lanzando comfy_batch.py ...")
        cmd = [sys.executable, "comfy_batch.py",
               "--comfy-url", URL,
               "--prompts", "./batch_prompts.json",
               "--out", "./outputs",
               "--workflow-video", WF]
        p = subprocess.run(cmd, cwd="/home/user/instalacion-confy")
        log(f"comfy_batch.py rc={p.returncode}")
        try:
            outs = [f for f in os.listdir("/home/user/instalacion-confy/outputs") if f.endswith(".mp4")]
            log(f"  MP4 en outputs: {outs}")
        except Exception:
            pass
    finally:
        log("Apagando y borrando pod (obligatorio)...")
        stop_delete()
        log("FIN.")

if __name__ == "__main__":
    main()
