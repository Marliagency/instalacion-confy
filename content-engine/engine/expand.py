#!/usr/bin/env python3
"""
expand.py — Expande el plan de la semana al manifiesto de piezas.

    plan.json + plantillas/<t>.json + marcas/<m>/estilo.json  ->  manifest.json

Cada item del plan (template + marca + vars) se convierte en una PIEZA con sus
TOMAS concretas (un prompt por toma, con la semilla derivada de forma
determinista). El expansor es idempotente: si el manifiesto ya existe, conserva
el estado y las salidas de las piezas existentes (no regenera trabajo hecho).

Uso:
    python3 engine/expand.py 2026-W23
"""

import sys
import zlib

from common import (
    PLANTILLAS_DIR, MARCAS_DIR, log, warn,
    load_json, load_manifest, save_manifest, paths_semana,
    merge_config, render_vars, formato_dims, canal_a_formato,
)
import os


def _seed_for(pieza_id, toma_idx, vars_dict):
    """Semilla determinista: misma pieza/toma/vars -> misma semilla (reproducible)."""
    base = f"{pieza_id}|{toma_idx}|{sorted(vars_dict.items())}"
    return zlib.crc32(base.encode("utf-8")) & 0x7FFFFFFF


def _cargar_plantilla(nombre):
    path = os.path.join(PLANTILLAS_DIR, f"{nombre}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"No existe la plantilla '{nombre}' ({path})")
    return load_json(path)


def _cargar_estilo(marca):
    path = os.path.join(MARCAS_DIR, marca, "estilo.json")
    return load_json(path, default={}) if os.path.exists(path) else {}


def _resolver_formatos(item, cfg):
    """Formatos de la pieza: explícitos, derivados del canal, o los de config."""
    if item.get("formatos"):
        return list(item["formatos"])
    if item.get("canal"):
        return [canal_a_formato(item["canal"])]
    return list(cfg["formatos"])


def construir_pieza(item, idx, cfg, plantillas_cache, estilos_cache):
    pieza_id = item.get("id") or f"p{idx + 1:03d}"
    marca = item.get("marca", "default")
    tname = item["template"]

    if tname not in plantillas_cache:
        plantillas_cache[tname] = _cargar_plantilla(tname)
    if marca not in estilos_cache:
        estilos_cache[marca] = _cargar_estilo(marca)

    plantilla = plantillas_cache[tname]
    estilo = estilos_cache[marca]

    # vars efectivas = estilo de marca + vars del item (el item gana).
    vars_eff = dict(estilo.get("vars", {}))
    vars_eff.update(item.get("vars", {}))

    sufijo = estilo.get("sufijo_prompt", "")
    negativo_base = estilo.get("negativo", "")
    w, h = None, None  # la resolución de generación la pone el workflow/estilo
    res = estilo.get("resolucion")
    if isinstance(res, (list, tuple)) and len(res) == 2:
        w, h = int(res[0]), int(res[1])

    tomas = []
    for ti, toma in enumerate(plantilla.get("tomas", [])):
        prompt = render_vars(toma.get("prompt", ""), vars_eff)
        if sufijo:
            prompt = f"{prompt}, {sufijo}".strip(", ")
        negativo = render_vars(toma.get("negativo", negativo_base), vars_eff)
        tomas.append({
            "idx": ti,
            "prompt": prompt,
            "negativo": negativo,
            "seed": item.get("seed_base", 0) + _seed_for(pieza_id, ti, vars_eff),
            "width": w,
            "height": h,
            "frame": None,
        })

    titular = render_vars(item.get("titular") or plantilla.get("titular", ""), vars_eff)
    cta = render_vars(item.get("cta") or plantilla.get("cta", ""), vars_eff)

    return {
        "id": pieza_id,
        "template": tname,
        "marca": marca,
        "vars": vars_eff,
        "titular": titular,
        "cta": cta,
        "canal": item.get("canal"),
        "dia": item.get("dia"),
        "pilar": item.get("pilar"),
        "formatos": _resolver_formatos(item, cfg),
        "audio": item.get("audio"),
        "tomas": tomas,
        "estado": "prompt",
        "error": None,
        "salidas": {},
    }


def _recuperar_frames(pieza, viejo):
    """Reasocia rutas de frames ya existentes en disco (resumible, sin regastar GPU)."""
    por_idx = {t["idx"]: t for t in viejo.get("tomas", [])}
    for t in pieza["tomas"]:
        vt = por_idx.get(t["idx"])
        if vt and vt.get("frame") and os.path.exists(vt["frame"]):
            t["frame"] = vt["frame"]


def expand(semana, reintentar=False):
    p = paths_semana(semana)
    if not os.path.exists(p["plan"]):
        raise SystemExit(f"No existe el plan {p['plan']}. Crea la semana con new_week.py.")

    plan = load_json(p["plan"])
    cfg = merge_config(plan.get("config"))
    items = plan.get("items", [])
    if not items:
        raise SystemExit("El plan no tiene 'items'.")

    # Conserva estado previo de piezas ya procesadas.
    prev = {pz["id"]: pz for pz in load_manifest(semana).get("piezas", [])}

    plantillas_cache, estilos_cache = {}, {}
    piezas = []
    nuevas = conservadas = revividas = 0
    for i, item in enumerate(items):
        pieza = construir_pieza(item, i, cfg, plantillas_cache, estilos_cache)
        viejo = prev.get(pieza["id"])
        if viejo:
            _recuperar_frames(pieza, viejo)
            estado_viejo = viejo.get("estado")
            if estado_viejo in ("generado", "final"):
                pieza["estado"] = estado_viejo
                pieza["salidas"] = viejo.get("salidas", {})
                conservadas += 1
            elif estado_viejo == "error":
                if reintentar:
                    # Revive: si ya tiene todos los frames, salta GPU (-> generado).
                    completo = all(t.get("frame") for t in pieza["tomas"])
                    pieza["estado"] = "generado" if completo else "prompt"
                    revividas += 1
                else:
                    pieza["estado"] = "error"
                    pieza["error"] = viejo.get("error")
                    pieza["salidas"] = viejo.get("salidas", {})
                    conservadas += 1
            else:
                nuevas += 1  # estaba en plan/prompt: se re-expande como prompt
        else:
            nuevas += 1
        piezas.append(pieza)

    manifest = {"semana": semana, "config": cfg, "piezas": piezas}
    save_manifest(semana, manifest)

    n_tomas = sum(len(pz["tomas"]) for pz in piezas)
    extra = f", {revividas} revividas" if revividas else ""
    log(f"[expand] {len(piezas)} piezas ({nuevas} nuevas, {conservadas} conservadas{extra}), "
        f"{n_tomas} tomas. Formatos por defecto: {cfg['formatos']}")
    return manifest


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Uso: python3 engine/expand.py <SEMANA> [--reintentar]")
    expand(sys.argv[1], reintentar="--reintentar" in sys.argv)


if __name__ == "__main__":
    main()
