#!/usr/bin/env python3
"""
runpod_ctl.py — Control del pod de RunPod por API (encender / apagar / estado).

Pensado para el modo AUTONOMÍA TOTAL: Claude lo usa desde la sesión web para
arrancar el pod antes de un lote y apagarlo en cuanto termina, minimizando coste.

Requiere la variable de entorno RUNPOD_API_KEY.

Uso:
    python3 runpod_ctl.py status [POD_ID]
    python3 runpod_ctl.py list
    python3 runpod_ctl.py start  POD_ID [--wait] [--wait-comfy]
    python3 runpod_ctl.py stop   POD_ID
    python3 runpod_ctl.py url    POD_ID            # imprime la URL de ComfyUI (8188)

Notas:
    - La URL pública de ComfyUI es determinista: https://<POD_ID>-8188.proxy.runpod.net
    - --wait        espera a que el pod quede en estado RUNNING.
    - --wait-comfy  además espera a que ComfyUI responda en /system_stats
                    (los modelos grandes tardan en cargar tras arrancar).
    - Usa la API REST de RunPod (https://rest.runpod.io/v1). Si algún endpoint
      cambiara, ajustar BASE/endpoints abajo.
"""

import argparse
import json
import os
import sys
import time

import requests

BASE = "https://rest.runpod.io/v1"
DEFAULT_POD_ID = "gy9p9fryeh1yex"  # pod del usuario (ver CLAUDE.md); verificar con 'list'


def _headers():
    key = os.environ.get("RUNPOD_API_KEY")
    if not key:
        sys.exit("ERROR: falta la variable de entorno RUNPOD_API_KEY.")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def comfy_url(pod_id):
    return f"https://{pod_id}-8188.proxy.runpod.net"


def api(method, path, **kw):
    r = requests.request(method, f"{BASE}{path}", headers=_headers(), timeout=30, **kw)
    if r.status_code >= 400:
        raise RuntimeError(f"RunPod API {method} {path} -> HTTP {r.status_code}: {r.text[:500]}")
    if r.text.strip():
        try:
            return r.json()
        except ValueError:
            return r.text
    return None


def list_pods():
    data = api("GET", "/pods")
    pods = data if isinstance(data, list) else data.get("pods", data)
    return pods


def get_pod(pod_id):
    return api("GET", f"/pods/{pod_id}")


def start_pod(pod_id):
    return api("POST", f"/pods/{pod_id}/start")


def stop_pod(pod_id):
    return api("POST", f"/pods/{pod_id}/stop")


def _status_of(pod):
    if not isinstance(pod, dict):
        return "?"
    return (pod.get("desiredStatus") or pod.get("status")
            or pod.get("currentStatus") or "?")


def wait_running(pod_id, timeout=600, interval=10):
    start = time.time()
    while time.time() - start < timeout:
        st = _status_of(get_pod(pod_id))
        print(f"    estado del pod: {st}")
        if str(st).upper() == "RUNNING":
            return True
        time.sleep(interval)
    raise TimeoutError(f"El pod {pod_id} no llegó a RUNNING en {timeout}s")


def wait_comfy(pod_id, timeout=900, interval=10):
    url = comfy_url(pod_id)
    start = time.time()
    last = None
    while time.time() - start < timeout:
        try:
            r = requests.get(f"{url}/system_stats", timeout=10)
            if r.status_code == 200:
                print(f"    ComfyUI listo en {url}")
                return True
            last = f"HTTP {r.status_code}"
        except Exception as e:  # noqa: BLE001
            last = str(e)
        print(f"    esperando a ComfyUI... ({last})")
        time.sleep(interval)
    raise TimeoutError(f"ComfyUI no respondió en {timeout}s ({url})")


def main():
    ap = argparse.ArgumentParser(description="Control de pod RunPod por API.")
    ap.add_argument("action", choices=["status", "list", "start", "stop", "url"])
    ap.add_argument("pod_id", nargs="?", default=DEFAULT_POD_ID)
    ap.add_argument("--wait", action="store_true", help="esperar a estado RUNNING")
    ap.add_argument("--wait-comfy", action="store_true", help="esperar a que ComfyUI responda")
    args = ap.parse_args()

    if args.action == "list":
        for p in list_pods():
            if isinstance(p, dict):
                print(f"{p.get('id')}  {_status_of(p):10}  {p.get('name','')}  "
                      f"{(p.get('machine') or {}).get('gpuTypeId','')}")
            else:
                print(p)
        return

    if args.action == "url":
        print(comfy_url(args.pod_id))
        return

    if args.action == "status":
        pod = get_pod(args.pod_id)
        print(json.dumps(pod, indent=2, ensure_ascii=False) if isinstance(pod, dict) else pod)
        print(f"\nestado: {_status_of(pod)}")
        print(f"ComfyUI: {comfy_url(args.pod_id)}")
        return

    if args.action == "start":
        print(f"[i] Arrancando pod {args.pod_id}...")
        start_pod(args.pod_id)
        if args.wait or args.wait_comfy:
            wait_running(args.pod_id)
        if args.wait_comfy:
            wait_comfy(args.pod_id)
        print(f"[i] OK. ComfyUI: {comfy_url(args.pod_id)}")
        return

    if args.action == "stop":
        print(f"[i] Apagando pod {args.pod_id}...")
        stop_pod(args.pod_id)
        print("[i] Orden de stop enviada.")
        return


if __name__ == "__main__":
    main()
