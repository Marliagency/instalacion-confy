#!/usr/bin/env python3
"""studio_webhook.py — Entrypoint para n8n: un webhook = un vídeo.

n8n NO reimplementa nada: solo dispara este entrypoint con un JSON
{ "slug": "...", "brief": "...", "max_cost": N } (por arg, stdin o env WEBHOOK_JSON)
y este script ejecuta `studio.py make`. Lotes baratos: automáticos (--yes implícito
si max_cost cubre el coste). Lotes caros o con assets faltantes: `make` para y este
entrypoint devuelve el plan/lista por stdout y un exit code != 0 para que n8n espere
aprobación.

Uso (en el pod):
    python3 studio_webhook.py '{"slug":"marli","brief":"anuncio UGC 30s ...","max_cost":3}'
    echo '{...}' | python3 studio_webhook.py
"""
import json, os, sys, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    args = sys.argv[1:]
    if args and args[0] == "--b64":  # JSON en base64 (robusto ante comillas en el brief)
        import base64
        raw = base64.b64decode(args[1]).decode("utf-8")
    else:
        raw = (args[0] if args else None) or os.environ.get("WEBHOOK_JSON") or sys.stdin.read()
    try:
        req = json.loads(raw)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"JSON inválido: {e}"})); sys.exit(2)

    slug = req.get("slug"); brief = req.get("brief")
    if not slug or not brief:
        print(json.dumps({"ok": False, "error": "faltan 'slug' y/o 'brief'"})); sys.exit(2)
    max_cost = str(req.get("max_cost", 5))

    cmd = [sys.executable, os.path.join(HERE, "studio.py"), "make", slug,
           "--brief", brief, "--max-cost", max_cost]
    if req.get("name"):
        cmd += ["--name", req["name"]]
    if req.get("blueprint"):
        cmd += ["--blueprint", req["blueprint"]]
    # Aprobación: por defecto NO forzamos --yes; make se detiene si el coste supera
    # max_cost y devuelve el plan. n8n reintenta con {"approve": true} para forzar.
    if req.get("approve"):
        cmd += ["--yes"]

    p = subprocess.run(cmd, capture_output=True, text=True)
    out = p.stdout + ("\n" + p.stderr if p.stderr else "")
    result = {"ok": p.returncode == 0, "exit": p.returncode, "slug": slug, "log": out[-6000:]}
    if p.returncode == 0:
        vid = os.path.join("projects", slug, "outputs")
        result["outputs_dir"] = vid
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if p.returncode == 0 else 1)


if __name__ == "__main__":
    main()
