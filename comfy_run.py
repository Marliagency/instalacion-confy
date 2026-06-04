#!/usr/bin/env python3
"""
comfy_run.py — Runner genérico de ComfyUI dirigido por el paquete de producción.

Para cada segmento cuyo motor sea de ComfyUI (wan_i2v / wan_lipsync), carga la
plantilla YA VALIDADA (workflows/api/*.json), le inyecta los valores del
segmento (imagen base, prompt de movimiento, resolución, frames, semilla, audio)
y encola el clip. Descarga a outputs/clips/<id>.mp4.

NO reconstruye grafos: solo carga + inyecta. Los formatos slideshow (ffmpeg) y
el montaje final se hacen en local (build_slideshow.py / assemble_final.py).

    python3 comfy_run.py --comfy-url https://POD-8188.proxy.runpod.net \
        --package examples/marli_ad01.json --out outputs/clips
"""
import argparse, os, random
import pipeline, formats
from run_i2v import queue, wait, download   # reutiliza la comunicación con ComfyUI

GPU_ENGINES = {"wan_i2v", "wan_lipsync"}


def positive_for(seg, pkg):
    """Prompt positivo para i2v: escena + movimiento + cámara."""
    im = (seg.get("imagen") or {})
    base = pipeline.inject_style(im.get("prompt", ""), pkg)
    an = seg.get("animacion") or {}
    parts = [base]
    if an.get("prompt_movimiento"): parts.append(an["prompt_movimiento"])
    if an.get("camara"): parts.append(f"camera: {an['camara']}")
    return ", ".join(p for p in parts if p)


def run_segment(base_url, seg_resolved, pkg, out_dir, audio_dir):
    seg = seg_resolved["seg"]; engine = seg_resolved["engine"]; uid = seg_resolved["uid"]
    graph, inj = formats.load_template(engine)          # lanza claro si pendiente_validar
    w, h = formats.ASPECT_WAN_WH.get(pkg["salida"]["aspecto"], (480, 832))
    frames = seg.get("frames") or int(round(seg.get("duracion_s", 5) * 16))
    seed = seg.get("seed") or random.randint(0, 2**31 - 1)
    params = {
        "image": seg_resolved.get("start_image") or f"{uid}.png",  # retrato del personaje si aplica
        "positive": positive_for(seg, pkg),
        "negative": (seg.get("imagen") or {}).get("negativo", "blurry, low quality, watermark, text"),
        "width": w, "height": h, "length": frames, "seed": seed, "prefix": uid,
    }
    if engine == "wan_lipsync":
        params["audio"] = f"{uid}.wav"   # voz del avatar (tts) subida al input del pod
    wf = formats.inject(graph, inj, params)
    print(f"  [{seg_resolved['order']}] {uid} ({engine}, {w}x{h}, {frames}f, seed {seed})", flush=True)
    pid = queue(base_url, wf)
    outs = wait(base_url, pid)
    saved = download(base_url, outs, out_dir, uid)
    print(f"      OK -> {[os.path.basename(s) for s in saved]}", flush=True)
    return saved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--comfy-url", required=True)
    ap.add_argument("--package", required=True)
    ap.add_argument("--out", default="outputs/clips")
    ap.add_argument("--audio-dir", default="outputs/voice")
    args = ap.parse_args()
    base = args.comfy_url.rstrip("/")
    os.makedirs(args.out, exist_ok=True)
    pkg = pipeline.load_package(args.package)
    segs = [s for s in pipeline.iter_segments(pkg) if s["engine"] in GPU_ENGINES]
    print(f"[i] {len(segs)} segmentos de ComfyUI (los slideshow se montan en local)")
    ok, fail = [], []
    for s in segs:
        try:
            run_segment(base, s, pkg, args.out, args.audio_dir)
            ok.append(s["id"])
        except Exception as e:
            print(f"      ERROR {s['id']}: {e}", flush=True)
            fail.append({"id": s["id"], "error": str(e)})
    print(f"\nRESUMEN comfy_run: OK={len(ok)} FAIL={len(fail)}")
    for f in fail: print("  -", f["id"], f["error"][:160])


if __name__ == "__main__":
    main()
