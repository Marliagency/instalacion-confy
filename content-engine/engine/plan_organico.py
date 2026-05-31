#!/usr/bin/env python3
"""
plan_organico.py — Planificador de contenido orgánico.

Convierte la INTENCIÓN de la semana (estrategia: total, canales, temas, mezcla de
pilares) en un plan.json equilibrado + un calendario.csv (día · canal · pilar ·
titular). Tú (o Claude Code) das la estrategia; este script hace la distribución.

    semanas/<W>/intencion.json  ->  semanas/<W>/plan.json  +  calendario.csv

Reparto:
  1. La mezcla de pilares (pesos) decide cuántas piezas va a cada pilar
     (método del mayor resto, suma exacta = total).
  2. Dentro de cada pilar se rota entre sus plantillas (pilares.json) y entre los
     temas de la intención.
  3. Se interleavan los pilares y se reparten canal (rota) y día (a lo largo de la
     semana); el formato sale del canal automáticamente.
  4. A cada pieza se le pone un titular/gancho hook-first generado del pilar.

Uso:
    python3 engine/plan_organico.py 2026-W24
"""

import argparse
import csv
import os

from common import (
    PILARES_FILE, log, warn, load_json, save_json,
    paths_semana, canal_a_formato, merge_config, render_vars,
)

DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def _reparto_mayor_resto(total, pesos):
    """Reparte `total` enteros según `pesos` (dict pilar->peso), suma exacta."""
    s = sum(pesos.values()) or 1.0
    exactos = {k: total * v / s for k, v in pesos.items()}
    base = {k: int(v) for k, v in exactos.items()}
    faltan = total - sum(base.values())
    # Asigna los restos a los mayores residuos (orden estable por nombre).
    restos = sorted(pesos, key=lambda k: (exactos[k] - base[k], k), reverse=True)
    for k in restos[:faltan]:
        base[k] += 1
    return base


def _gancho(pilar_def, tema, idx):
    hooks = pilar_def.get("hooks") or ["{tema}"]
    patron = hooks[idx % len(hooks)]
    return render_vars(patron, {"tema": tema}).strip()


def planificar(semana):
    p = paths_semana(semana)
    if not os.path.exists(p["intencion"]):
        raise SystemExit(
            f"No existe {p['intencion']}. Crea la intención de la semana "
            "(total, canales, temas, mezcla)."
        )
    intencion = load_json(p["intencion"])
    pilares_doc = load_json(PILARES_FILE, default={"pilares": {}})
    pilares = pilares_doc.get("pilares", {})
    if not pilares:
        raise SystemExit(f"{PILARES_FILE} no define pilares.")

    marca = intencion.get("marca", "default")
    total = int(intencion.get("total", 0))
    canales = intencion.get("canales") or ["tiktok"]
    temas = intencion.get("temas") or ["general"]
    mezcla = intencion.get("mezcla") or {k: v.get("peso", 0) for k, v in pilares.items()}
    # Solo pilares conocidos y con peso > 0.
    mezcla = {k: float(v) for k, v in mezcla.items() if k in pilares and v > 0}
    if total <= 0 or not mezcla:
        raise SystemExit("La intención necesita 'total' > 0 y una 'mezcla' válida.")

    reparto = _reparto_mayor_resto(total, mezcla)
    log(f"[plan-organico] {total} piezas — reparto por pilar: " +
        ", ".join(f"{k}={n}" for k, n in reparto.items() if n))

    # Construye colas por pilar.
    colas = {}
    for pilar, n in reparto.items():
        if n <= 0:
            continue
        pdef = pilares[pilar]
        plantillas = pdef.get("plantillas") or ["dato"]
        cola = []
        for i in range(n):
            tema = temas[i % len(temas)]
            template = plantillas[i % len(plantillas)]
            titular = _gancho(pdef, tema, i)
            cola.append({"pilar": pilar, "template": template, "tema": tema,
                         "titular": titular,
                         "cta": pdef.get("cta", "Síguenos para más")})
        colas[pilar] = cola

    # Interleave por pilares (round-robin) para mezclar la semana.
    orden = sorted(colas, key=lambda k: -reparto[k])
    piezas = []
    while any(colas[k] for k in orden):
        for k in orden:
            if colas[k]:
                piezas.append(colas[k].pop(0))

    # Asigna canal (rota) y día (repartido a lo largo de la semana).
    items = []
    filas_cal = []
    n = len(piezas)
    for i, pz in enumerate(piezas):
        canal = canales[i % len(canales)]
        formato = canal_a_formato(canal)
        dia = DIAS[(i * 7) // n] if n else DIAS[0]
        pid = f"o{i + 1:03d}"
        items.append({
            "id": pid,
            "template": pz["template"],
            "marca": marca,
            "canal": canal,
            "dia": dia,
            "pilar": pz["pilar"],
            "formatos": [formato],
            "titular": pz["titular"],
            "cta": pz["cta"],
            "vars": {
                "tema": pz["tema"],
                "titular": pz["titular"],
                "idea": pz["tema"],
                "tip": pz["tema"],
                "cta": pz["cta"],
            },
        })
        filas_cal.append([dia, canal, pz["pilar"], pz["template"], pid, pz["titular"]])

    cfg = merge_config(intencion.get("config"))
    cfg["formatos"] = sorted({canal_a_formato(c) for c in canales})
    plan = {"semana": semana, "config": cfg, "items": items}
    save_json(p["plan"], plan)

    with open(p["calendario"], "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["dia", "canal", "pilar", "template", "id", "titular"])
        w.writerows(filas_cal)

    log(f"[plan-organico] escrito plan.json ({len(items)} items) y calendario.csv")
    return plan


def main():
    ap = argparse.ArgumentParser(description="Planificador de contenido orgánico.")
    ap.add_argument("semana")
    args = ap.parse_args()
    planificar(args.semana)


if __name__ == "__main__":
    main()
