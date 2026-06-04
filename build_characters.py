#!/usr/bin/env python3
"""
build_characters.py — Genera los retratos de los personajes persistentes UNA vez.

Usa el mejor modelo de OpenAI (gpt-image-1, calidad por defecto 'high') y guarda
el retrato en assets/characters/<id>.png. Si ya existe, lo REUTILIZA (no regenera)
→ el personaje se mantiene idéntico en todos los vídeos y ahorras imágenes.

Se ejecuta DENTRO del pod (OpenAI bloqueado en local). Requiere OPENAI_API_KEY.

    OPENAI_API_KEY=... python3 build_characters.py --package paquete.json
"""
import argparse, os, sys
import pipeline
from openai_images import generate_image


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", required=True)
    ap.add_argument("--force", action="store_true", help="regenerar aunque el retrato exista")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    pkg = pipeline.load_package(args.package)
    size = pipeline.image_size(pkg)  # retrato vertical (9:16 -> 1024x1536)
    chars = list(pipeline.iter_characters(pkg))
    if not chars:
        print("El paquete no define 'personajes'."); return
    key = os.environ.get("OPENAI_API_KEY")
    if not args.dry_run and not key:
        sys.exit("Falta OPENAI_API_KEY (in-pod).")
    for c in chars:
        out = c["retrato"]
        if os.path.isfile(out) and not args.force:
            print(f"  {c['id']}: REUTILIZADO ({out}) — no se regenera"); continue
        print(f"  {c['id']}: gpt-image-1 {c['calidad']} -> {out}", flush=True)
        if args.dry_run:
            continue
        png = generate_image(c["prompt"], size, key, quality=c["calidad"], model="gpt-image-1",
                             ref_paths=None)
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with open(out, "wb") as f:
            f.write(png)
        print(f"     OK ({len(png)//1024} KB)")


if __name__ == "__main__":
    main()
