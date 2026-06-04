#!/usr/bin/env python3
"""
fetch_models.py — Descargador inteligente de modelos para la Sesión 2 (in-pod).

Minimiza descargas: baja SOLO lo que el paquete necesita.
- i2v (cinematic/pov/product/screen_demo/hands_asmr): los modelos WAN 2.2 los trae el
  flag del template `download_wan22=true` (automático). Aquí no se tocan.
- ugc (lip-sync): el stack de InfiniteTalk NO viene en el template → se baja aquí, y
  SOLO si el paquete tiene segmentos `ugc`. Idempotente (salta lo que ya existe).

Descarga en paralelo (wget -c) a /ComfyUI/models/<dir>. Reutilizable y determinista.

    python3 fetch_models.py --package paquete.json [--comfy /ComfyUI] [--only-lipsync]
"""
import argparse, os, subprocess, sys
import pipeline

KJ = "https://huggingface.co/Kijai/WanVideo_comfy/resolve/main"
CO21 = "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files"

# Stack InfiniteTalk (lip-sync) — validado en LIPSYNC.md. (dir, url)
LIPSYNC_MODELS = [
    ("diffusion_models", f"{KJ}/Wan2_1-I2V-14B-480P_fp8_e4m3fn.safetensors"),
    ("diffusion_models", f"{KJ}/InfiniteTalk/Wan2_1-InfiniTetalk-Single_fp16.safetensors"),
    ("vae",              f"{KJ}/Wan2_1_VAE_bf16.safetensors"),
    ("text_encoders",    f"{KJ}/umt5-xxl-enc-bf16.safetensors"),
    ("clip_vision",      f"{CO21}/clip_vision/clip_vision_h.safetensors"),
    ("loras",            f"{KJ}/Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors"),
]


def needed_engines(pkg):
    return {s["engine"] for s in pipeline.iter_segments(pkg)}


def download(models, comfy):
    procs = []
    for sub, url in models:
        dst = os.path.join(comfy, "models", sub)
        os.makedirs(dst, exist_ok=True)
        fn = url.split("/")[-1]
        if os.path.isfile(os.path.join(dst, fn)) and os.path.getsize(os.path.join(dst, fn)) > 1e6:
            print(f"  REUSE {sub}/{fn}"); continue
        print(f"  GET   {sub}/{fn}", flush=True)
        procs.append(subprocess.Popen(["wget", "-q", "-c", "-P", dst, url]))
    rc = [p.wait() for p in procs]
    return all(r == 0 for r in rc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", required=True)
    ap.add_argument("--comfy", default="/ComfyUI")
    ap.add_argument("--only-lipsync", action="store_true")
    args = ap.parse_args()
    pkg = pipeline.load_package(args.package)
    engines = needed_engines(pkg)
    print(f"[i] motores en el lote: {sorted(engines)}")
    if "wan_lipsync" in engines or args.only_lipsync:
        print("[i] hay UGC -> descargando stack InfiniteTalk (solo lo que falte):")
        ok = download(LIPSYNC_MODELS, args.comfy)
        print(f"[i] lip-sync stack: {'OK' if ok else 'algún fallo'}")
    else:
        print("[i] sin UGC -> no hace falta descargar nada extra (i2v via download_wan22).")
    print("[i] (wav2vec se auto-descarga en la primera generación)")


if __name__ == "__main__":
    main()
