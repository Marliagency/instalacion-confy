#!/usr/bin/env python3
"""
comfy_doctor.py — Verifica que los workflows guardados siguen siendo válidos
contra el pod actual (auto-detecta "drift" si cambia la imagen/los modelos).

Compara los `modelos_requeridos` de cada workflows/api/*.json con las listas
reales que expone ComfyUI en /object_info (UNETLoader, CLIPLoader, VAELoader,
LoraLoaderModelOnly). Si falta algún archivo, avisa ANTES de gastar GPU.

    python3 comfy_doctor.py --comfy-url https://POD-8188.proxy.runpod.net
"""
import argparse, glob, json, sys
import requests

LOADER_FIELD = {
    "unet":  ("UNETLoader", "unet_name"),
    "loras": ("LoraLoaderModelOnly", "lora_name"),
    "clip":  ("CLIPLoader", "clip_name"),
    "vae":   ("VAELoader", "vae_name"),
}


def available(oi, node, field):
    try:
        return set(oi[node]["input"]["required"][field][0])
    except Exception:
        return set()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--comfy-url", required=True)
    ap.add_argument("--glob", default="workflows/api/*.json")
    args = ap.parse_args()
    base = args.comfy_url.rstrip("/")
    oi = requests.get(f"{base}/object_info", timeout=60).json()
    have = {k: available(oi, n, f) for k, (n, f) in LOADER_FIELD.items()}
    problems = 0
    for path in sorted(glob.glob(args.glob)):
        data = json.load(open(path))
        meta = data.get("_meta", {})
        if meta.get("pendiente_validar"):
            print(f"… {path}: PENDIENTE DE VALIDAR (omitido)")
            continue
        req = meta.get("modelos_requeridos", {})
        missing = []
        for kind, files in req.items():
            for fn in files:
                if fn not in have.get(kind, set()):
                    missing.append(f"{kind}:{fn}")
        if missing:
            problems += 1
            print(f"✗ {path}: FALTAN {len(missing)} modelos")
            for m in missing: print(f"     - {m}")
        else:
            print(f"✓ {path}: OK")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
