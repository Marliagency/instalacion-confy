#!/usr/bin/env python3
"""
assemble_pkg.py — Montaje final dirigido por el PAQUETE de producción (Fase 2).

Toma los clips de cada segmento (outputs/clips/<id>.mp4, generados por comfy_run
+ build_slideshow), los ordena según el paquete, quema el texto en pantalla de
los segmentos que no son slideshow (los slideshow ya traen sus tarjetas),
encadena con crossfade, añade la tarjeta de cierre de marca, y mezcla el audio:
voz por segmento (outputs/voice/<id>.mp3 avatar | <id>_vo.mp3 voz en off) colocada
en su momento + colchón de música (salida.musica.ruta u outputs/music.mp3).

    python3 assemble_pkg.py --package examples/marli_ad01.json --out outputs/marli_final.mp4

Reutiliza el estilo de marca (Inter, rojo, lower-third, tarjeta de cierre) de
assemble_final.py. Lienzo: af.W x af.H (1080x1920).
"""
import argparse, os, subprocess, sys
import pipeline
import assemble_final as af   # caption_clip, outro_card, dur, run, W, H, FPS, T

VOICE_DIR = "outputs/voice"


def normalize_clip(src, out):
    af.run(["ffmpeg", "-y", "-i", src, "-an",
            "-vf", f"scale={af.W}:{af.H}:force_original_aspect_ratio=increase,"
                   f"crop={af.W}:{af.H},setsar=1,fps={af.FPS},format=yuv420p",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", out])
    return out


# formatos que YA llevan su texto dentro del clip (no añadir lower-third encima)
SELF_CAPTIONED = {"slideshow", "kinetic_text", "stat_reveal", "before_after"}


def build_video(segs, pkg, tmp, cierre):
    """Genera los clips normalizados/captionados + tarjeta de cierre (de UNA pieza)."""
    clips, durs = [], []
    for i, s in enumerate(segs):
        seg = s["seg"]; uid = s["uid"]
        src = os.path.join("outputs/clips", f"{uid}.mp4")
        if not os.path.isfile(src):
            sys.exit(f"Falta el clip {src} (¿generaste comfy_run / build_slideshow?).")
        out = os.path.join(tmp, f"v_{uid}.mp4")
        texto = seg.get("texto_pantalla")
        if texto and seg["formato"] not in SELF_CAPTIONED:
            af.caption_clip(src, texto, out, tmp, i)
        else:
            normalize_clip(src, out)
        clips.append(out); durs.append(af.dur(out))
    if cierre:
        oc, od = af.outro_card(os.path.join(tmp, "outro.mp4"), tmp)
        clips.append(oc); durs.append(od)
    return clips, durs


def segment_offsets(durs):
    """Inicio de cada segmento en la línea de tiempo con crossfade T."""
    offs, t = [], 0.0
    for i, d in enumerate(durs):
        offs.append(max(0.0, t))
        t += d - af.T
    return offs


def voice_jobs(segs, offsets):
    """Lista (ruta_audio, offset_s) de las voces a colocar (por uid)."""
    jobs = []
    for s, off in zip(segs, offsets):
        uid = s["uid"]
        for cand in (f"{uid}.mp3", f"{uid}_vo.mp3"):
            p = os.path.join(VOICE_DIR, cand)
            if os.path.isfile(p):
                jobs.append((p, off + 0.2))
    return jobs


def build_audio(jobs, music_path, total_s, out, ugc_windows=None):
    """Mezcla música (baja) + voces colocadas por offset. Devuelve out o None.

    REGLA: la música se SILENCIA durante las ventanas UGC (ugc_windows = [(a,b)…]),
    para no pisar la voz del avatar (los UGC llevan su propio audio).
    """
    if not jobs and not (music_path and os.path.isfile(music_path)):
        return None
    inputs, fc, labels = [], [], []
    idx = 0
    if music_path and os.path.isfile(music_path):
        inputs += ["-i", music_path]
        gain = "0.5"
        for a, b in (ugc_windows or []):
            gain = f"({gain})*(1-between(t,{a:.3f},{b:.3f}))"   # 0 durante UGC
        fc.append(f"[{idx}:a]volume=eval=frame:volume='{gain}',"
                  f"afade=t=in:st=0:d=1.5,afade=t=out:st={max(0,total_s-2):.2f}:d=2,"
                  f"atrim=0:{total_s:.2f}[m]")
        labels.append("[m]"); idx += 1
    for p, off in jobs:
        inputs += ["-i", p]
        fc.append(f"[{idx}:a]adelay={int(off*1000)}|{int(off*1000)},volume=1.25[v{idx}]")
        labels.append(f"[v{idx}]"); idx += 1
    fc.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0,alimiter=limit=0.95[a]")
    af.run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(fc),
            "-map", "[a]", "-c:a", "aac", "-b:a", "192k", out])
    return out


def assemble_piece(pieza_id, segs, pkg, out_dir, tmp, no_audio):
    """Monta UNA pieza (sus segmentos) en out_dir/<pieza_id>.mp4."""
    cierre = next((p.get("cierre_marca", True) for p in pkg["piezas"] if p["id"] == pieza_id), True)
    ptmp = os.path.join(tmp, pieza_id); os.makedirs(ptmp, exist_ok=True)
    clips, durs = build_video(segs, pkg, ptmp, cierre)
    inputs = []
    for c in clips: inputs += ["-i", c]
    fc = []; prev = "[0:v]"; total = durs[0]
    for i in range(1, len(clips)):
        off = max(0.0, total - af.T); lbl = f"[x{i}]"
        fc.append(f"{prev}[{i}:v]xfade=transition=fade:duration={af.T}:offset={off:.3f}{lbl}")
        prev = lbl; total = total + durs[i] - af.T
    video_only = os.path.join(ptmp, "video.mp4")
    af.run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(fc), "-map", prev,
            "-c:v", "libx264", "-preset", "slow", "-crf", "19", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", "-r", str(af.FPS), video_only])
    total_s = af.dur(video_only)
    out = os.path.join(out_dir, f"{pieza_id}.mp4")
    audio = None
    if not no_audio:
        offsets = segment_offsets(durs)
        # REGLA: ventanas UGC donde la música se silencia (el avatar lleva su voz)
        ugc_windows = [(offsets[i], offsets[i] + durs[i])
                       for i, s in enumerate(segs) if s["formato"] == "ugc"]
        music = (pkg["salida"].get("musica") or {}).get("ruta") or "outputs/music.mp3"
        audio = build_audio(voice_jobs(segs, offsets), music, total_s,
                            os.path.join(ptmp, "audio.m4a"), ugc_windows=ugc_windows)
    if audio:
        af.run(["ffmpeg", "-y", "-i", video_only, "-i", audio, "-map", "0:v", "-map", "1:a",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", out])
    else:
        af.run(["ffmpeg", "-y", "-i", video_only, "-c", "copy", "-movflags", "+faststart", out])
    print(f"  PIEZA {pieza_id} -> {out}  ({af.dur(out):.1f}s){'' if audio else '  [sin audio]'}", flush=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", required=True)
    ap.add_argument("--out-dir", default="outputs", help="carpeta de salida; un MP4 por pieza")
    ap.add_argument("--no-audio", action="store_true", help="solo vídeo (validar sin voces/música)")
    args = ap.parse_args()
    pkg = pipeline.load_package(args.package)
    tmp = "/tmp/marli_pkg"; os.makedirs(tmp, exist_ok=True)
    os.makedirs(args.out_dir, exist_ok=True)
    # agrupar segmentos por pieza (preservando orden)
    by_piece = {}
    for s in pipeline.iter_segments(pkg):
        by_piece.setdefault(s["pieza_id"], []).append(s)
    print(f"[i] {len(by_piece)} pieza(s) -> {len(by_piece)} vídeo(s)")
    outs = []
    for pid, segs in by_piece.items():
        outs.append(assemble_piece(pid, segs, pkg, args.out_dir, tmp, args.no_audio))
    print(f"\nFINAL: {len(outs)} vídeo(s) en {args.out_dir}/")


if __name__ == "__main__":
    main()
