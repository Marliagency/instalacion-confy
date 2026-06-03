#!/usr/bin/env python3
"""
review.py — Genera contact sheets para el control de calidad de la S3 (editor).

Por cada clip crea una tira de fotogramas (para juzgar movimiento/calidad sin abrir
el vídeo); por las imágenes, una rejilla. El editor (Claude) abre estos PNG con la
herramienta de lectura de imágenes y decide qué tomas valen.

    python3 review.py --dir outputs --out outputs/review
"""
import argparse, glob, json, os, subprocess


def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return p.returncode == 0


def dur(path):
    o = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nokey=1:noprint_wrappers=1", path],
                       stdout=subprocess.PIPE, text=True).stdout.strip()
    try: return float(o)
    except Exception: return 5.0


def clip_sheet(clip, out, cols=5):
    """Tira de `cols` fotogramas equiespaciados del clip."""
    d = dur(clip)
    fps = max(0.5, cols / max(0.1, d))   # ~cols fotogramas en total
    ok = run(["ffmpeg", "-y", "-i", clip,
              "-vf", f"fps={fps:.4f},scale=240:-1,tile={cols}x1",
              "-frames:v", "1", out])
    return ok


def grid(images, out, cols=4):
    if not images: return False
    inputs = []
    for im in images: inputs += ["-i", im]
    fc = "".join(f"[{i}:v]scale=240:-1[s{i}];" for i in range(len(images)))
    fc += "".join(f"[s{i}]" for i in range(len(images)))
    rows = (len(images) + cols - 1) // cols
    fc += f"tile={cols}x{rows}[o]"
    return run(["ffmpeg", "-y", *inputs, "-filter_complex", fc, "-map", "[o]", "-frames:v", "1", out])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="outputs")
    ap.add_argument("--out", default="outputs/review")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    made = []
    # clips
    for clip in sorted(glob.glob(os.path.join(args.dir, "clips", "*.mp4"))):
        uid = os.path.splitext(os.path.basename(clip))[0]
        out = os.path.join(args.out, f"clip_{uid}.png")
        if clip_sheet(clip, out):
            made.append(out)
    # imágenes (rejilla por pieza si hay manifest, si no todas juntas)
    imgs = sorted(glob.glob(os.path.join(args.dir, "images", "*.png")))
    if imgs:
        out = os.path.join(args.out, "images_grid.png")
        if grid(imgs, out):
            made.append(out)
    print(f"[i] {len(made)} contact sheets en {args.out}/ — revísalos con la herramienta de imagen:")
    for m in made:
        print("   ", m)


if __name__ == "__main__":
    main()
