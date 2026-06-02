#!/usr/bin/env python3
"""
edit_video.py — Montaje/edición final del vídeo a partir de los clips generados.

Último paso del pipeline: toma los clips WAN (.mp4) descargados en ./outputs,
los normaliza al mismo formato (resolución/fps), los une con transiciones
crossfade, opcionalmente superpone una marca de texto (branding) y mezcla una
pista de música de fondo, y exporta un único MP4 listo para publicar.

Requiere ffmpeg + ffprobe (en el entorno web: `apt-get install -y ffmpeg`).

Ejemplos:
    # Une todos los .mp4 de ./outputs (orden alfabético) en un 9:16 con crossfades
    python3 edit_video.py --inputs "outputs/*.mp4" --out outputs/final.mp4

    # Orden explícito + música + marca + transición de 0.5s
    python3 edit_video.py \
        --inputs outputs/v01_*.mp4 outputs/v02_*.mp4 outputs/v03_*.mp4 \
        --music assets/track.mp3 --brand "marli agency" \
        --transition 0.5 --out outputs/final.mp4

El formato de salida por defecto es 9:16 (1080x1920) a 30 fps, H.264 yuv420p
con +faststart (reproducible en redes y móviles).
"""

import argparse
import glob
import json
import os
import subprocess
import sys
import tempfile


def run(cmd):
    """Ejecuta un comando y aborta con su salida si falla."""
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode != 0:
        sys.exit(f"ERROR ejecutando: {' '.join(cmd)}\n{p.stdout[-2000:]}")
    return p.stdout


def have(tool):
    from shutil import which
    return which(tool) is not None


def probe_duration(path):
    """Duración en segundos (float) vía ffprobe."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", path],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    ).stdout
    try:
        return float(json.loads(out)["format"]["duration"])
    except Exception:  # noqa: BLE001
        sys.exit(f"No pude leer la duración de {path}. ¿Es un vídeo válido?")


def expand_inputs(patterns):
    """Expande globs y mantiene el orden dado; ordena alfabéticamente dentro de cada glob."""
    files = []
    for pat in patterns:
        matches = sorted(glob.glob(pat)) if any(c in pat for c in "*?[") else [pat]
        if not matches:
            print(f"  (aviso) sin coincidencias para: {pat}")
        files.extend(matches)
    # de-dup conservando orden
    seen, ordered = set(), []
    for f in files:
        if f not in seen and os.path.isfile(f):
            seen.add(f)
            ordered.append(f)
    return ordered


def main():
    ap = argparse.ArgumentParser(description="Montaje final del vídeo con ffmpeg (concat + crossfade + música + branding).")
    ap.add_argument("--inputs", nargs="+", required=True, help="Clips de entrada (rutas o globs), en orden")
    ap.add_argument("--out", default="outputs/final.mp4", help="MP4 de salida")
    ap.add_argument("--width", type=int, default=1080)
    ap.add_argument("--height", type=int, default=1920)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--transition", type=float, default=0.4, help="Duración del crossfade entre clips (s); 0 = corte seco")
    ap.add_argument("--music", help="Pista de audio de fondo (mp3/wav/m4a)")
    ap.add_argument("--music-db", type=float, default=-3.0, help="Ganancia de la música en dB (negativo = más bajo)")
    ap.add_argument("--brand", help="Texto de marca a superponer (ej. 'marli agency')")
    ap.add_argument("--brand-size", type=int, default=48)
    args = ap.parse_args()

    if not have("ffmpeg") or not have("ffprobe"):
        sys.exit("Falta ffmpeg/ffprobe. Instala con: apt-get install -y ffmpeg")

    clips = expand_inputs(args.inputs)
    if not clips:
        sys.exit("No hay clips de entrada válidos.")
    print(f"[i] {len(clips)} clips:")
    for c in clips:
        print(f"    - {c}")

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    W, H, FPS, T = args.width, args.height, args.fps, args.transition

    durations = [probe_duration(c) for c in clips]

    # --- filtro: normaliza cada clip (escala+pad al lienzo, fps, sar, sin audio) ---
    fc = []
    for i, _c in enumerate(clips):
        fc.append(
            f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"setsar=1,fps={FPS},format=yuv420p[v{i}]"
        )

    # --- cadena de transiciones (xfade) o concat simple ---
    if len(clips) == 1:
        last = "[v0]"
    elif T > 0:
        prev = "[v0]"
        total = durations[0]
        for i in range(1, len(clips)):
            off = max(0.0, total - T)
            out = f"[x{i}]"
            fc.append(f"{prev}[v{i}]xfade=transition=fade:duration={T}:offset={off:.3f}{out}")
            prev = out
            total = total + durations[i] - T
        last = prev
    else:
        ins = "".join(f"[v{i}]" for i in range(len(clips)))
        fc.append(f"{ins}concat=n={len(clips)}:v=1:a=0[vcat]")
        last = "[vcat]"

    # --- branding opcional (drawtext en esquina inferior) ---
    if args.brand:
        txt = args.brand.replace(":", r"\:").replace("'", r"\'")
        out = "[vbr]"
        fc.append(
            f"{last}drawtext=text='{txt}':fontcolor=white@0.85:fontsize={args.brand_size}:"
            f"x=(w-text_w)/2:y=h-text_h-80:box=1:boxcolor=black@0.35:boxborderw=18{out}"
        )
        last = out

    # --- música opcional ---
    inputs = []
    for c in clips:
        inputs += ["-i", c]
    cmd = ["ffmpeg", "-y"] + inputs

    if args.music:
        if not os.path.isfile(args.music):
            sys.exit(f"No existe la pista de música: {args.music}")
        total_dur = sum(durations) - max(0, len(clips) - 1) * (T if T > 0 else 0)
        cmd += ["-stream_loop", "-1", "-i", args.music]
        music_idx = len(clips)
        fade_out_start = max(0.0, total_dur - 1.5)
        fc.append(
            f"[{music_idx}:a]volume={args.music_db}dB,"
            f"afade=t=in:st=0:d=1.0,afade=t=out:st={fade_out_start:.3f}:d=1.5,"
            f"atrim=0:{total_dur:.3f}[aout]"
        )
        map_audio = ["-map", "[aout]", "-c:a", "aac", "-b:a", "192k", "-shortest"]
    else:
        map_audio = []

    filtergraph = ";".join(fc)
    cmd += [
        "-filter_complex", filtergraph,
        "-map", last,
    ] + map_audio + [
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-r", str(FPS), args.out,
    ]

    print(f"\n[i] Montando -> {args.out}  ({W}x{H} @ {FPS}fps, transición {T}s"
          f"{', con música' if args.music else ''}{', con marca' if args.brand else ''})")
    run(cmd)
    final_dur = probe_duration(args.out)
    size_mb = os.path.getsize(args.out) / (1024 * 1024)
    print(f"[i] OK: {args.out}  ({final_dur:.1f}s, {size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
