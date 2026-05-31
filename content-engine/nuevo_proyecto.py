#!/usr/bin/env python3
"""
nuevo_proyecto.py — La puerta de entrada: del INPUT DE DISEÑO a una semana lista.

Tú (o Claude Code) describes el proyecto UNA vez en un brief JSON y este script
crea todo lo necesario para empezar a generar:

  brief.json  ->  marcas/<proyecto>/(estilo.json + workflow.json + workflow.map.json)
              ->  semanas/<W>/intencion.json
              ->  semanas/<W>/plan.json + calendario.csv   (vía plan_organico)

Después solo queda:
    python3 engine/pipeline.py <W> --simular        # prueba sin GPU
    python3 ../produccion.py <W>                     # producción real en RunPod

Uso:
    python3 nuevo_proyecto.py briefs/aera.json
    python3 nuevo_proyecto.py briefs/aera.json 2026-W25
    python3 nuevo_proyecto.py --ejemplo             # escribe briefs/ejemplo.json

CAMPOS DEL BRIEF (briefs/<proyecto>.json):
    proyecto       (obligatorio) id corto de la marca, p.ej. "aera"
    marca          nombre visible de la marca
    descripcion    qué es / qué vende el proyecto
    estilo_visual  cómo deben verse las imágenes (clave del look)
    paleta         colores dominantes
    tono           voz de los textos
    negativo       qué evitar en las imágenes (prompt negativo)
    resolucion     [w, h] de generación (por defecto [1024,1024])
    canales        ["tiktok","ig-feed","youtube", ...]
    temas          lista de temas/ángulos de la semana
    productos      lista de productos (genera además piezas comerciales)
    total_semana   nº de piezas orgánicas de la semana (por defecto 12)
    mezcla         pesos por pilar {"educar":0.4, ...} (opcional)
    config         overrides del pipeline (fps, duracion_toma, editores, hosts...)
"""

import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from common import (  # noqa: E402
    MARCAS_DIR, paths_semana, load_json, save_json, log, warn,
)
import plan_organico  # noqa: E402


BRIEF_EJEMPLO = {
    "proyecto": "aera",
    "marca": "Aera",
    "descripcion": "Zapatillas de running ligeras para ciudad",
    "estilo_visual": "fotografía de producto limpia, fondo neutro, luz natural suave",
    "paleta": "tonos tierra, blanco roto y un acento coral",
    "tono": "cercano, motivador y sin tecnicismos",
    "negativo": "baja calidad, borroso, deforme, texto, marca de agua, logo ajeno",
    "resolucion": [1024, 1024],
    "canales": ["tiktok", "ig-feed", "youtube"],
    "temas": ["amortiguación", "ligereza", "running urbano", "rutina de calentamiento"],
    "productos": ["Zapatilla Aera One"],
    "total_semana": 12,
    "mezcla": {"educar": 0.4, "entretener": 0.3, "inspirar": 0.2, "comunidad": 0.1},
}


def _semana_por_defecto():
    """Devuelve la semana ISO actual como 'YYYY-Www'."""
    import datetime
    y, w, _ = datetime.date.today().isocalendar()
    return f"{y}-W{w:02d}"


def crear_marca(brief):
    """Crea marcas/<proyecto>/ con estilo + workflow listos para usar."""
    proyecto = brief["proyecto"]
    md = os.path.join(MARCAS_DIR, proyecto)
    os.makedirs(md, exist_ok=True)

    estilo_visual = brief.get("estilo_visual", "fotografía limpia, luz suave")
    paleta = brief.get("paleta", "")
    estilo_str = estilo_visual + (f", paleta {paleta}" if paleta else "")
    estilo = {
        "descripcion": brief.get("descripcion", proyecto),
        "vars": {
            "estilo": estilo_str,
            "marca": brief.get("marca", proyecto),
            "tono": brief.get("tono", ""),
        },
        "sufijo_prompt": "alta calidad, gran nitidez, composición profesional, 8k",
        "negativo": brief.get("negativo",
                              "baja calidad, borroso, deforme, texto, marca de agua, logo"),
        "resolucion": brief.get("resolucion", [1024, 1024]),
    }
    save_json(os.path.join(md, "estilo.json"), estilo)
    log(f"  + marcas/{proyecto}/estilo.json")

    # Copia el workflow + mapa de la marca 'default' como punto de partida, para
    # que la marca quede LISTA. El usuario puede sustituirlo por el suyo después.
    default = os.path.join(MARCAS_DIR, "default")
    for fname in ("workflow.json", "workflow.map.json"):
        dst = os.path.join(md, fname)
        src = os.path.join(default, fname)
        if not os.path.exists(dst):
            if os.path.exists(src):
                shutil.copyfile(src, dst)
                log(f"  + marcas/{proyecto}/{fname}  (copiado de default; sustitúyelo por el tuyo)")
            else:
                warn(f"No existe {src}; ejecuta new_week.py una vez para sembrar 'default'.")
    return proyecto


def crear_semana(brief, semana):
    """Escribe intencion.json y lanza el planificador orgánico."""
    p = paths_semana(semana)
    for d in (p["base"], p["inputs_audio"], p["generated"], p["edited"]):
        os.makedirs(d, exist_ok=True)

    intencion = {
        "marca": brief["proyecto"],
        "total": int(brief.get("total_semana", 12)),
        "canales": brief.get("canales", ["tiktok", "ig-feed", "youtube"]),
        "temas": brief.get("temas", ["general"]),
        "mezcla": brief.get("mezcla",
                            {"educar": 0.4, "entretener": 0.3, "inspirar": 0.2, "comunidad": 0.1}),
    }
    if brief.get("config"):
        intencion["config"] = brief["config"]
    save_json(p["intencion"], intencion)
    log(f"  + semanas/{semana}/intencion.json")

    plan_organico.planificar(semana)

    # Si hay productos, añade piezas comerciales al plan generado.
    productos = brief.get("productos") or []
    if productos:
        plan = load_json(p["plan"])
        base = len(plan["items"])
        for i, prod in enumerate(productos):
            plan["items"].append({
                "id": f"c{i + 1:03d}",
                "template": "producto",
                "marca": brief["proyecto"],
                "formatos": plan["config"]["formatos"],
                "vars": {
                    "producto": prod,
                    "titular": prod,
                    "cta": "Descúbrelo",
                    # 'estilo' NO se pone aquí: lo aporta marcas/<proyecto>/estilo.json
                },
            })
        save_json(p["plan"], plan)
        log(f"  + {len(productos)} pieza(s) comercial(es) de producto añadidas al plan "
            f"(total {base + len(productos)} items)")


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return
    if args[0] == "--ejemplo":
        os.makedirs(os.path.join(os.path.dirname(__file__), "briefs"), exist_ok=True)
        dest = os.path.join(os.path.dirname(__file__), "briefs", "ejemplo.json")
        save_json(dest, BRIEF_EJEMPLO)
        log(f"Brief de ejemplo escrito en {os.path.relpath(dest)}. Edítalo y luego:\n"
            f"  python3 nuevo_proyecto.py briefs/ejemplo.json")
        return

    brief_path = args[0]
    semana = args[1] if len(args) > 1 else _semana_por_defecto()
    brief = load_json(brief_path)
    if not brief.get("proyecto"):
        raise SystemExit("El brief necesita al menos el campo 'proyecto'.")

    log(f"== Nuevo proyecto '{brief['proyecto']}' -> semana {semana} ==")
    crear_marca(brief)
    crear_semana(brief, semana)
    log("\nListo. Siguiente paso:\n"
        f"  python3 engine/pipeline.py {semana} --simular     # prueba sin GPU\n"
        f"  python3 ../produccion.py {semana}                 # producción real (RunPod)")


if __name__ == "__main__":
    main()
