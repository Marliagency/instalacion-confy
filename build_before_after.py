#!/usr/bin/env python3
"""
build_before_after.py — Formato before_after SIN GPU (ffmpeg): wipe ANTES→DESPUÉS.

Usa 2 imágenes (<uid>_1.png = antes, <uid>_2.png = después) con etiquetas en rojo,
y una transición de barrido. Texto en MAYÚSCULAS (R3.2b). Salida outputs/clips/<uid>.mp4.

    python3 build_before_after.py --package paquete.json --images outputs/images --out outputs/clips
"""
import argparse, os, subprocess, sys
import pipeline

FONT_B = "assets/fonts/Inter-Bold.ttf"
RED, INK = "0xE24B4A", "0x141210"


def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode != 0:
        sys.exit("ERROR ffmpeg:\n" + p.stdout[-2000:])


def esc(p):
    return p.replace(":", "\\:")


def side(img, label, out, W, H, FPS, secs, tmp, tag):
    tf = os.path.join(tmp, f"ba_{tag}.txt"); open(tf, "w").write(label.upper())
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS},"
          f"format=yuv420p,"
          f"drawbox=x=60:y=120:w=260:h=92:color={INK}@0.55:t=fill,"
          f"drawtext=fontfile={FONT_B}:textfile={esc(tf)}:fontcolor={RED}:fontsize=54:"
          f"x=90:y=146:expansion=none")
    run(["ffmpeg", "-y", "-loop", "1", "-i", img, "-vf", vf, "-t", f"{secs:.2f}",
         "-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", out])


def before_after(seg, uid, W, H, FPS, out, imgdir, tmp):
    ims = seg.get("imagenes", [])
    a_img = os.path.join(imgdir, f"{uid}_1.png")
    b_img = os.path.join(imgdir, f"{uid}_2.png")
    if not (os.path.isfile(a_img) and os.path.isfile(b_img)):
        print(f"  {uid}: faltan {a_img} / {b_img}"); return False
    la = (ims[0].get("texto") if len(ims) > 0 and ims[0].get("texto") else "ANTES")
    lb = (ims[1].get("texto") if len(ims) > 1 and ims[1].get("texto") else "DESPUÉS")
    D = seg.get("duracion_s") or 5
    T = 0.6
    each = (D + T) / 2
    sa = os.path.join(tmp, f"{uid}_a.mp4"); sb = os.path.join(tmp, f"{uid}_b.mp4")
    side(a_img, la, sa, W, H, FPS, each, tmp, uid + "a")
    side(b_img, lb, sb, W, H, FPS, each, tmp, uid + "b")
    run(["ffmpeg", "-y", "-i", sa, "-i", sb, "-filter_complex",
         f"[0:v][1:v]xfade=transition=wiperight:duration={T}:offset={each-T:.2f}[v]",
         "-map", "[v]", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", "-r", str(FPS), out])
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", required=True)
    ap.add_argument("--images", default="outputs/images")
    ap.add_argument("--out", default="outputs/clips")
    args = ap.parse_args()
    pkg = pipeline.load_package(args.package)
    W, H = pkg["salida"]["resolucion"]; FPS = pkg["salida"].get("fps", 30)
    tmp = "/tmp/marli_ba"; os.makedirs(tmp, exist_ok=True)
    os.makedirs(args.out, exist_ok=True)
    made = 0
    for s in pipeline.iter_segments(pkg):
        if s["formato"] != "before_after":
            continue
        if before_after(s["seg"], s["uid"], W, H, FPS,
                        os.path.join(args.out, f"{s['uid']}.mp4"), args.images, tmp):
            made += 1; print("  before_after", s["uid"])
    print(f"Before/after construidos: {made}")


if __name__ == "__main__":
    main()
