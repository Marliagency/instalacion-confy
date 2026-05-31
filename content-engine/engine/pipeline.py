#!/usr/bin/env python3
"""
pipeline.py — Orquestador del Content Engine.

Encadena las tres fases sobre una semana:

    expand  ->  generate  ->  edit

    plan ─► prompt ─► generado ─► final
                         └────────► error   (un fallo NO tumba el lote)

Cada pieza avanza sola por la máquina de estados. Si falla, queda en 'error' con
su mensaje y el resto continúa. El proceso es resumible: re-ejecutar retoma donde
se quedó (los frames y vídeos ya hechos no se rehacen).

Uso:
    python3 engine/pipeline.py 2026-W23              # producción real
    python3 engine/pipeline.py 2026-W23 --simular    # sin GPU (frames de prueba)
    python3 engine/pipeline.py 2026-W23 --reintentar # reanuda solo las fallidas
"""

import argparse

from common import log, load_manifest, paths_semana
from expand import expand
from generate import generate
from edit import edit


def _resumen(semana):
    manifest = load_manifest(semana)
    conteo = {}
    for pz in manifest["piezas"]:
        conteo[pz["estado"]] = conteo.get(pz["estado"], 0) + 1
    p = paths_semana(semana)
    log("\n===== RESUMEN DE LA SEMANA " + semana + " =====")
    for estado in ("final", "generado", "prompt", "plan", "error"):
        if conteo.get(estado):
            log(f"  {estado:9s}: {conteo[estado]}")
    finales = sum(len(pz.get("salidas", {})) for pz in manifest["piezas"]
                  if pz["estado"] == "final")
    log(f"  vídeos finales: {finales}")
    if conteo.get("error"):
        log("  Piezas con error (usa --reintentar para reanudarlas):")
        for pz in manifest["piezas"]:
            if pz["estado"] == "error":
                log(f"    - {pz['id']}: {pz.get('error')}")
    log(f"  Vídeos en: {p['edited']}")


def run(semana, simular=False, reintentar=False, hosts=None):
    log(f"=== Content Engine · semana {semana} "
        f"{'[SIMULACIÓN]' if simular else '[REAL]'}"
        f"{' [REINTENTAR]' if reintentar else ''} ===")
    expand(semana, reintentar=reintentar)
    generate(semana, simular=simular, hosts_override=hosts)
    edit(semana)
    _resumen(semana)


def main():
    ap = argparse.ArgumentParser(description="Orquestador del Content Engine.")
    ap.add_argument("semana")
    ap.add_argument("--simular", action="store_true",
                    help="No usa GPU: frames de color de prueba (valida el flujo).")
    ap.add_argument("--reintentar", action="store_true",
                    help="Reanuda solo las piezas en estado 'error'.")
    ap.add_argument("--host", action="append", dest="hosts",
                    help="Sobrescribe los hosts de ComfyUI (repetible). "
                         "ip:puerto o URL completa https://... (lo usa produccion.py).")
    args = ap.parse_args()
    run(args.semana, simular=args.simular, reintentar=args.reintentar, hosts=args.hosts)


if __name__ == "__main__":
    main()
