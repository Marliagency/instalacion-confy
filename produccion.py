#!/usr/bin/env python3
"""
produccion.py — Producción REAL del Content Engine sobre RunPod (un solo comando).

Orquesta el ciclo completo minimizando coste:

    arrancar pod -> esperar ComfyUI -> comprobar checkpoint de imagen ->
    generar+editar (motor) -> descargar a edited/ -> APAGAR EL POD (siempre)

ComfyUI corre en el pod (GPU); ffmpeg corre aquí (local). Los frames se descargan
por el proxy y la edición es local, así que solo pagas la GPU el tiempo justo de
generar las imágenes.

Uso:
    python3 produccion.py 2026-W25                 # pod por defecto (CLAUDE.md)
    python3 produccion.py 2026-W25 --pod POD_ID
    python3 produccion.py 2026-W25 --no-stop       # NO apaga el pod al terminar
    python3 produccion.py 2026-W25 --solo-comprobar # arranca, comprueba y apaga

Requiere RUNPOD_API_KEY y red hacia *.proxy.runpod.net.
SEGURIDAD DE COSTE: si el pod hay que arrancarlo, esto gasta GPU. El pod se apaga
SIEMPRE al terminar (salvo --no-stop), incluso si la generación falla.
"""

import argparse
import os
import subprocess
import sys

import requests

import runpod_ctl as rp

ROOT = os.path.dirname(os.path.abspath(__file__))
PIPELINE = os.path.join(ROOT, "content-engine", "engine", "pipeline.py")


def checkpoints_disponibles(url):
    """Lista los checkpoints de imagen visibles para ComfyUI (vía /object_info)."""
    try:
        r = requests.get(f"{url}/object_info/CheckpointLoaderSimple", timeout=30)
        r.raise_for_status()
        info = r.json()
        node = info.get("CheckpointLoaderSimple", info)
        opts = node["input"]["required"]["ckpt_name"][0]
        return list(opts) if isinstance(opts, list) else []
    except Exception as e:  # noqa: BLE001
        print(f"[aviso] no pude leer /object_info: {e}")
        return []


def main():
    ap = argparse.ArgumentParser(description="Producción real del Content Engine en RunPod.")
    ap.add_argument("semana")
    ap.add_argument("--pod", default=rp.DEFAULT_POD_ID)
    ap.add_argument("--no-stop", action="store_true", help="No apagar el pod al terminar.")
    ap.add_argument("--solo-comprobar", action="store_true",
                    help="Arranca, comprueba ComfyUI/checkpoint y apaga (no genera).")
    ap.add_argument("--reintentar", action="store_true", help="Pasa --reintentar al motor.")
    args = ap.parse_args()

    pod = args.pod
    url = rp.comfy_url(pod)
    arrancado_por_nosotros = False

    try:
        estado = rp._status_of(rp.get_pod(pod)).upper()
        print(f"[i] Pod {pod} estado: {estado}")
        if estado != "RUNNING":
            print("[i] Arrancando pod...")
            rp.start_pod(pod)
            rp.wait_running(pod)
            arrancado_por_nosotros = True
        print("[i] Esperando a que ComfyUI responda...")
        rp.wait_comfy(pod)

        cks = checkpoints_disponibles(url)
        print(f"[i] Checkpoints de imagen en el pod: {cks or '(ninguno)'}")
        if not cks:
            print(
                "\n[!] No hay checkpoint SDXL en el pod, así que el Content Engine\n"
                "    (imágenes) no puede generar todavía. Instala UNO una sola vez en\n"
                "    el volumen del pod, en models/checkpoints/ (terminal/Jupyter del\n"
                "    pod), por ejemplo un SDXL base o SDXL-Turbo. Luego repite este\n"
                "    comando. El pod se apagará ahora para no gastar GPU."
            )
            if args.solo_comprobar:
                return
            return  # el finally apaga el pod

        if args.solo_comprobar:
            print("[i] Comprobación OK. Apagando el pod.")
            return

        # --- Generación real: el motor habla con el ComfyUI del pod por el proxy ---
        cmd = [sys.executable, PIPELINE, args.semana, "--host", url]
        if args.reintentar:
            cmd.append("--reintentar")
        print(f"[i] Lanzando motor:\n    {' '.join(cmd)}\n")
        rc = subprocess.call(cmd)
        if rc != 0:
            print(f"[aviso] el motor terminó con código {rc}")

    finally:
        if args.no_stop:
            print(f"[i] --no-stop: el pod {pod} sigue ENCENDIDO. Acuérdate de apagarlo:")
            print(f"      python3 runpod_ctl.py stop {pod}")
        else:
            print(f"[i] Apagando el pod {pod} (obligatorio por coste)...")
            try:
                rp.stop_pod(pod)
                print("[i] Orden de stop enviada.")
            except Exception as e:  # noqa: BLE001
                print(f"[ERROR] no pude apagar el pod: {e}\n"
                      f"        APÁGALO MANUALMENTE: python3 runpod_ctl.py stop {pod}")


if __name__ == "__main__":
    main()
