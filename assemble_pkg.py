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


def build_video(segs, pkg, tmp):
    """Genera los clips normalizados/captionados + tarjeta de cierre. Devuelve (clips, durs)."""
    clips, durs = [], []
    for i, s in enumerate(segs):
        seg = s["seg"]; sid = seg["id"]
        src = os.path.join("outputs/clips", f"{sid}.mp4")
        if not os.path.isfile(src):
            sys.exit(f"Falta el clip {src} (¿generaste comfy_run / build_slideshow?).")
        out = os.path.join(tmp, f"v_{sid}.mp4")
        texto = seg.get("texto_pantalla")
        if texto and seg["formato"] != "slideshow":
            af.caption_clip(src, texto, out, tmp, i)
        else:
            normalize_clip(src, out)
        clips.append(out); durs.append(af.dur(out))
    # tarjeta de cierre
    if pkg["piezas"][0].get("cierre_marca", True):
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
    """Lista (ruta_audio, offset_s) de las voces a colocar."""
    jobs = []
    for s, off in zip(segs, offsets):
        sid = s["seg"]["id"]
        for cand in (f"{sid}.mp3", f"{sid}_vo.mp3"):
            p = os.path.join(VOICE_DIR, cand)
            if os.path.isfile(p):
                jobs.append((p, off + 0.2))
    return jobs


def build_audio(jobs, music_path, total_s, out):
    """Mezcla música (baja) + voces colocadas por offset. Devuelve out o None."""
    if not jobs and not (music_path and os.path.isfile(music_path)):
        return None
    inputs, fc, labels = [], [], []
    idx = 0
    if music_path and os.path.isfile(music_path):
        inputs += ["-i", music_path]
        fc.append(f"[{idx}:a]volume=0.5,afade=t=in:st=0:d=1.5,"
                  f"afade=t=out:st={max(0,total_s-2):.2f}:d=2,atrim=0:{total_s:.2f}[m]")
        labels.append("[m]"); idx += 1
    for p, off in jobs:
        inputs += ["-i", p]
        fc.append(f"[{idx}:a]adelay={int(off*1000)}|{int(off*1000)},volume=1.25[v{idx}]")
        labels.append(f"[v{idx}]"); idx += 1
    fc.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0,alimiter=limit=0.95[a]")
    af.run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(fc),
            "-map", "[a]", "-c:a", "aac", "-b:a", "192k", out])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", required=True)
    ap.add_argument("--out", default="outputs/marli_final.mp4")
    ap.add_argument("--no-audio", action="store_true", help="solo vídeo (para validar sin voces/música)")
    args = ap.parse_args()
    pkg = pipeline.load_package(args.package)
    segs = list(pipeline.iter_segments(pkg))
    tmp = "/tmp/marli_pkg"; os.makedirs(tmp, exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)

    clips, durs = build_video(segs, pkg, tmp)
    # cadena de vídeo con crossfade
    inputs = []
    for c in clips: inputs += ["-i", c]
    fc = []; prev = "[0:v]"; total = durs[0]
    for i in range(1, len(clips)):
        off = max(0.0, total - af.T)
        lbl = f"[x{i}]"
        fc.append(f"{prev}[{i}:v]xfade=transition=fade:duration={af.T}:offset={off:.3f}{lbl}")
        prev = lbl; total = total + durs[i] - af.T
    video_only = os.path.join(tmp, "video.mp4")
    af.run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(fc), "-map", prev,
            "-c:v", "libx264", "-preset", "slow", "-crf", "19", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", "-r", str(af.FPS), video_only])
    total_s = af.dur(video_only)

    audio = None
    if not args.no_audio:
        offsets = segment_offsets(durs)
        music = (pkg["salida"].get("musica") or {}).get("ruta") or "outputs/music.mp3"
        audio = build_audio(voice_jobs(segs, offsets), music, total_s, os.path.join(tmp, "audio.m4a"))

    if audio:
        af.run(["ffmpeg", "-y", "-i", video_only, "-i", audio, "-map", "0:v", "-map", "1:a",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                "-shortest", args.out])
    else:
        af.run(["ffmpeg", "-y", "-i", video_only, "-c", "copy", "-movflags", "+faststart", args.out])
    print(f"\nFINAL -> {args.out}  ({af.dur(args.out):.1f}s, {os.path.getsize(args.out)/1e6:.1f} MB)"
          f"{'  [sin audio]' if not audio else ''}")


if __name__ == "__main__":
    main()
