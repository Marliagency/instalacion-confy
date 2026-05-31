#!/usr/bin/env python3
"""
generate.py — Genera los frames de cada pieza con ComfyUI (multi-GPU).

Recorre el manifiesto y, para cada toma de cada pieza en estado 'prompt',
inyecta el prompt/semilla en el workflow de su marca y lo genera en ComfyUI.
Las tomas se reparten entre todos los `hosts` (una instancia por GPU) mediante
una cola: cada worker tira tareas de la cola en cuanto su GPU queda libre, así
que el reparto es automático y equilibrado.

Tolerante a fallos:
  - reintentos por toma (config.reintentos),
  - si el frame ya existe en disco, NO se regenera (no se regasta GPU),
  - si una pieza falla, queda en estado 'error' y el resto continúa.

Modo --simular: no contacta ComfyUI; crea frames de color de prueba con ffmpeg
(útil para validar todo el pipeline sin gastar GPU).

Uso:
    python3 engine/generate.py 2026-W23 [--simular]
"""

import argparse
import os
import queue
import subprocess
import threading

from common import (
    MARCAS_DIR, log, warn, load_json,
    load_manifest, save_manifest, paths_semana,
)
import comfy


# ---------------------------------------------------------------------------
# Carga de workflow + mapa por marca (con caché)
# ---------------------------------------------------------------------------
def _cargar_marca(marca, cache):
    if marca in cache:
        return cache[marca]
    wpath = os.path.join(MARCAS_DIR, marca, "workflow.json")
    mpath = os.path.join(MARCAS_DIR, marca, "workflow.map.json")
    if not os.path.exists(wpath):
        raise FileNotFoundError(f"Falta {wpath} (exporta tu workflow en formato API)")
    wf = load_json(wpath)
    mapa = load_json(mpath, default={}) if os.path.exists(mpath) else {}
    cache[marca] = (wf, mapa)
    return cache[marca]


# ---------------------------------------------------------------------------
# Frame de prueba (modo --simular)
# ---------------------------------------------------------------------------
_COLORES = ["1f6f8b", "8a5082", "6b7a8f", "f1a661", "3c6e71", "b5651d",
            "284b63", "9a348e", "39a0ca", "e07a5f"]


def _frame_simulado(dest, etiqueta, idx):
    color = _COLORES[idx % len(_COLORES)]
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"color=c=0x{color}:s=1024x1024",
        "-frames:v", "1", dest,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return dest


# ---------------------------------------------------------------------------
# Generación de una toma (con reintentos)
# ---------------------------------------------------------------------------
def _generar_toma(host, marca_cache, pieza, toma, dest, simular, reintentos, gen_timeout):
    # Resumible: si ya hay frame, no se regasta GPU.
    if toma.get("frame") and os.path.exists(toma["frame"]):
        return toma["frame"]
    if os.path.exists(dest):
        return dest

    if simular:
        return _frame_simulado(dest, pieza["id"], toma["idx"])

    wf, mapa = _cargar_marca(pieza["marca"], marca_cache)
    last = None
    for intento in range(reintentos + 1):
        try:
            inj = comfy.inject(
                wf, mapa,
                prompt=toma["prompt"], negativo=toma.get("negativo"),
                seed=toma.get("seed"), width=toma.get("width"), height=toma.get("height"),
            )
            return comfy.generar_imagen(host, inj, dest, gen_timeout=gen_timeout)
        except Exception as e:  # noqa: BLE001
            last = e
            warn(f"{pieza['id']} t{toma['idx']} intento {intento + 1} falló: {e}")
    raise RuntimeError(f"toma {toma['idx']}: {last}")


# ---------------------------------------------------------------------------
# Orquestación con cola de trabajo repartida entre hosts
# ---------------------------------------------------------------------------
def generate(semana, simular=False, hosts_override=None):
    manifest = load_manifest(semana)
    cfg = manifest["config"]
    p = paths_semana(semana)
    gen_dir = p["generated"]
    os.makedirs(gen_dir, exist_ok=True)

    hosts = list(hosts_override or cfg.get("hosts") or ["127.0.0.1:8188"])
    reintentos = int(cfg.get("reintentos", 2))
    gen_timeout = int(cfg.get("gen_timeout", 600))

    if not simular:
        vivos = [h for h in hosts if comfy.ping(h)]
        if not vivos:
            raise SystemExit(
                f"Ningún host de ComfyUI responde: {hosts}. "
                "Arranca ComfyUI o usa --simular para probar sin GPU."
            )
        if len(vivos) < len(hosts):
            warn(f"Hosts sin responder, se ignoran: {set(hosts) - set(vivos)}")
        hosts = vivos
    log(f"[generate] {'SIMULACIÓN' if simular else 'REAL'} — hosts: {hosts}")

    # Selecciona piezas pendientes (estado 'prompt') y monta la lista de tareas.
    pendientes = [pz for pz in manifest["piezas"] if pz.get("estado") == "prompt"]
    if not pendientes:
        log("[generate] nada pendiente (todas generadas o finales).")
        return manifest

    marca_cache = {}
    lock = threading.Lock()
    tareas = queue.Queue()
    # Cada tarea: (pieza, toma). El estado por pieza se resuelve al final.
    fallos_por_pieza = {pz["id"]: [] for pz in pendientes}
    pendientes_por_pieza = {pz["id"]: 0 for pz in pendientes}
    for pz in pendientes:
        for toma in pz["tomas"]:
            tareas.put((pz, toma))
            pendientes_por_pieza[pz["id"]] += 1

    def worker(host):
        while True:
            try:
                pz, toma = tareas.get_nowait()
            except queue.Empty:
                return
            dest = os.path.join(gen_dir, f"{pz['id']}_t{toma['idx']}.png")
            try:
                ruta = _generar_toma(host, marca_cache, pz, toma, dest,
                                     simular, reintentos, gen_timeout)
                with lock:
                    toma["frame"] = ruta
                    log(f"  [{host}] {pz['id']} t{toma['idx']} OK")
            except Exception as e:  # noqa: BLE001
                with lock:
                    fallos_por_pieza[pz["id"]].append(str(e))
                    warn(f"{pz['id']} t{toma['idx']} ERROR DEFINITIVO: {e}")
            finally:
                with lock:
                    pendientes_por_pieza[pz["id"]] -= 1
                tareas.task_done()

    hilos = [threading.Thread(target=worker, args=(h,), daemon=True) for h in hosts]
    for t in hilos:
        t.start()
    for t in hilos:
        t.join()

    # Resuelve el estado de cada pieza y persiste.
    ok = err = 0
    for pz in pendientes:
        fallos = fallos_por_pieza[pz["id"]]
        tiene_todos = all(t.get("frame") and os.path.exists(t["frame"]) for t in pz["tomas"])
        if fallos or not tiene_todos:
            pz["estado"] = "error"
            pz["error"] = "; ".join(fallos) or "faltan frames"
            err += 1
        else:
            pz["estado"] = "generado"
            pz["error"] = None
            ok += 1

    save_manifest(semana, manifest)
    log(f"[generate] piezas generadas: {ok} · con error: {err}")
    return manifest


def main():
    ap = argparse.ArgumentParser(description="Genera frames con ComfyUI (multi-GPU).")
    ap.add_argument("semana")
    ap.add_argument("--simular", action="store_true",
                    help="No usa GPU: crea frames de color de prueba con ffmpeg.")
    ap.add_argument("--host", action="append", dest="hosts",
                    help="Sobrescribe los hosts de ComfyUI (repetible). "
                         "Acepta ip:puerto o una URL completa https://...")
    args = ap.parse_args()
    generate(args.semana, simular=args.simular, hosts_override=args.hosts)


if __name__ == "__main__":
    main()
