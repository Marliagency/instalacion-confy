#!/usr/bin/env python3
"""Orquestador autónomo: reintenta arrancar el pod hasta que haya GPU libre,
espera a ComfyUI, genera el lote y APAGA el pod siempre."""
import os, sys, time, subprocess, requests

POD = "gy9p9fryeh1yex"
URL = f"https://{POD}-8188.proxy.runpod.net"
BASE = "https://rest.runpod.io/v1"
H = {"Authorization": f"Bearer {os.environ['RUNPOD_API_KEY']}", "Content-Type": "application/json"}

# Cuánto tiempo seguir reintentando el arranque (segundos)
MAX_WAIT_START = int(os.environ.get("MAX_WAIT_START", "5400"))  # 90 min
START_INTERVAL = 30

def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)

def try_start():
    r = requests.post(f"{BASE}/pods/{POD}/start", headers=H, timeout=40)
    return r.status_code, r.text[:160]

def status():
    r = requests.get(f"{BASE}/pods/{POD}", headers=H, timeout=30)
    d = r.json() if r.text.strip() else {}
    return d.get("desiredStatus") or d.get("status") or "?"

def wait_running(timeout=600):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = status()
        log(f"  estado pod: {st}")
        if str(st).upper() == "RUNNING":
            return True
        time.sleep(10)
    return False

def wait_comfy(timeout=1200):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            r = requests.get(f"{URL}/system_stats", timeout=10)
            if r.status_code == 200:
                log(f"  ComfyUI LISTO en {URL}")
                return True
            last = f"HTTP {r.status_code}"
        except Exception as e:
            last = str(e)[:60]
        log(f"  esperando ComfyUI... {last}")
        time.sleep(10)
    return False

def stop():
    try:
        r = requests.post(f"{BASE}/pods/{POD}/stop", headers=H, timeout=40)
        log(f"  STOP -> HTTP {r.status_code}")
    except Exception as e:
        log(f"  STOP error: {e}")

def main():
    log(f"Orquestador iniciado. Reintentando arrancar {POD} hasta {MAX_WAIT_START}s.")
    started = False
    t0 = time.time()
    while time.time() - t0 < MAX_WAIT_START:
        code, txt = try_start()
        if code < 300:
            log(f"  START ACEPTADO (HTTP {code})")
            started = True
            break
        log(f"  start HTTP {code}: {txt}")
        time.sleep(START_INTERVAL)

    if not started:
        log("NO se consiguió GPU dentro del límite. Abortando sin gastar.")
        sys.exit(2)

    try:
        if not wait_running():
            log("El pod no llegó a RUNNING.")
            stop(); sys.exit(3)
        if not wait_comfy():
            log("ComfyUI no respondió.")
            stop(); sys.exit(4)

        log("Lanzando comfy_batch.py ...")
        cmd = [sys.executable, "comfy_batch.py",
               "--comfy-url", URL,
               "--prompts", "./batch_prompts.json",
               "--out", "./outputs",
               "--workflow-video", "./workflows/wan_t2v.json"]
        p = subprocess.run(cmd, cwd="/home/user/instalacion-confy")
        log(f"comfy_batch.py terminó con código {p.returncode}")
    finally:
        log("Apagando pod (obligatorio)...")
        stop()
        log("FIN.")

if __name__ == "__main__":
    main()
