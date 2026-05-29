#!/usr/bin/env python3
"""
check_setup.py — Verifica que tu Mac está listo para usar el pipeline.

No genera nada ni gasta GPU. Solo comprueba prerrequisitos y te dice qué falta.

Uso:
    python3 check_setup.py

Opcional, si ya tienes un pod encendido y quieres comprobar la conexión:
    python3 check_setup.py --comfy-url https://XXXX-8188.proxy.runpod.net
"""

import argparse
import os
import shutil
import subprocess
import sys

OK = "[ OK ]"
WARN = "[WARN]"
FAIL = "[FALTA]"


def check(label, condition, detail_ok="", detail_fail="", warn=False):
    tag = OK if condition else (WARN if warn else FAIL)
    line = f"{tag} {label}"
    detail = detail_ok if condition else detail_fail
    if detail:
        line += f"\n        {detail}"
    print(line)
    return condition


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--comfy-url", help="Si lo pasas, prueba la conexión con ComfyUI")
    args = ap.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    problems = 0

    print("=== Comprobación del pipeline (RunPod + ComfyUI) ===\n")

    # 1. Python
    pyok = sys.version_info >= (3, 9)
    if not check("Python 3.9+", pyok,
                 f"versión {sys.version.split()[0]}",
                 f"tienes {sys.version.split()[0]}, instala 3.9 o superior"):
        problems += 1

    # 2. Dependencias del script puente
    deps_ok = True
    for mod in ("requests", "websocket"):
        try:
            __import__(mod)
        except ImportError:
            deps_ok = False
    if not check("Dependencias (requests, websocket-client)", deps_ok,
                 "instaladas",
                 "ejecuta: pip3 install -r requirements.txt"):
        problems += 1

    # 3. Node.js (para el MCP de RunPod)
    node = shutil.which("node")
    node_ver = ""
    if node:
        try:
            node_ver = subprocess.check_output([node, "--version"], text=True).strip()
        except Exception:
            node_ver = "?"
    if not check("Node.js 18+ (para el MCP de RunPod)", bool(node),
                 f"{node_ver}",
                 "instala la versión LTS desde https://nodejs.org"):
        problems += 1

    # 4. API key de RunPod
    key = os.environ.get("RUNPOD_API_KEY", "")
    if not check("RUNPOD_API_KEY en el entorno", bool(key),
                 f"detectada (······{key[-4:]})" if key else "",
                 'añade: echo \'export RUNPOD_API_KEY="tu_key"\' >> ~/.zshrc ; source ~/.zshrc'):
        problems += 1

    # 5. Workflows
    img_wf = os.path.join(here, "workflows", "sdxl_t2i.json")
    vid_wf = os.path.join(here, "workflows", "wan_t2v.json")
    if not check("Workflow de imágenes (workflows/sdxl_t2i.json)", os.path.exists(img_wf),
                 "presente (recuerda ajustar el checkpoint)",
                 "falta el archivo del repo"):
        problems += 1
    check("Workflow de video (workflows/wan_t2v.json)", os.path.exists(vid_wf),
          "presente",
          "expórtalo desde ComfyUI (Save API Format). Sin él, solo podrás generar imágenes.",
          warn=True)

    # 6. Conexión opcional con ComfyUI
    if args.comfy_url:
        try:
            import requests
            r = requests.get(args.comfy_url.rstrip("/") + "/system_stats", timeout=10)
            check("Conexión con ComfyUI", r.status_code == 200,
                  "ComfyUI responde",
                  f"respondió HTTP {r.status_code}")
        except Exception as e:  # noqa: BLE001
            check("Conexión con ComfyUI", False, "", f"no respondió: {e}")
            problems += 1

    print()
    if problems == 0:
        print(">> Todo listo. Abre Claude Code en esta carpeta y pide tu lote.")
    else:
        print(f">> Faltan {problems} cosa(s). Resuélvelas (arriba) y vuelve a ejecutar.")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
