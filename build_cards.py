#!/usr/bin/env python3
"""
build_cards.py — Formatos de texto SIN GPU (ffmpeg): kinetic_text y stat_reveal.

Producen outputs/clips/<uid>.mp4 con identidad Marli (Inter, rojo, crema) y TODO el
texto en MAYÚSCULAS (R3.2b). Los consume el montaje igual que cualquier otro clip.

    python3 build_cards.py --package paquete.json --out outputs/clips
"""
import argparse, os, subprocess, sys
import pipeline

FONT_B = "assets/fonts/Inter-Bold.ttf"
FONT_M = "assets/fonts/Inter-Medium.ttf"
RED, CREAM, INK = "0xE24B4A", "0xFAF6F1", "0x2C2C2C"


def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode != 0:
        sys.exit("ERROR ffmpeg:\n" + p.stdout[-2000:])


def esc(p):
    return p.replace(":", "\\:")


def kinetic(seg, uid, W, H, FPS, out, tmp):
    lines = [l.upper() for l in (seg.get("lineas") or [seg.get("texto_pantalla") or ""]) if l]
    if not lines:
        lines = ["MARLI"]
    D = seg.get("duracion_s") or max(2.5, 1.4 * len(lines))
    per = D / len(lines)
    draws = [f"drawbox=x=(iw-160)/2:y=(h/2)-170:w=160:h=10:color={RED}:t=fill"]
    for i, l in enumerate(lines):
        tf = os.path.join(tmp, f"k_{uid}_{i}.txt"); open(tf, "w").write(l)
        a, b = i * per, (i + 1) * per
        alpha = (f"if(lt(t,{a+0.3:.2f}),max(0,(t-{a:.2f})/0.3),"
                 f"if(gt(t,{b-0.3:.2f}),max(0,({b:.2f}-t)/0.3),1))")
        draws.append(f"drawtext=fontfile={FONT_B}:textfile={esc(tf)}:fontcolor={INK}:fontsize=92:"
                     f"line_spacing=16:x=(w-text_w)/2:y=(h-text_h)/2:expansion=none:"
                     f"alpha='{alpha}':enable='between(t,{a:.2f},{b:.2f})'")
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={CREAM}:s={W}x{H}:d={D}:r={FPS}",
         "-vf", ",".join(draws), "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", "-r", str(FPS), out])


def stat(seg, uid, W, H, FPS, out, tmp):
    num = (seg.get("texto_pantalla") or "").upper()
    sub = (seg.get("subtexto") or "").upper()
    D = seg.get("duracion_s") or 4
    tn = os.path.join(tmp, f"n_{uid}.txt"); open(tn, "w").write(num)
    ts = os.path.join(tmp, f"s_{uid}.txt"); open(ts, "w").write(sub)
    fade = "if(lt(t,0.4),t/0.4,1)"
    vf = (f"drawtext=fontfile={FONT_B}:textfile={esc(tn)}:fontcolor={RED}:fontsize=240:"
          f"x=(w-text_w)/2:y=(h-text_h)/2-120:expansion=none:alpha='{fade}',"
          f"drawbox=x=(iw-200)/2:y=h/2+70:w=200:h=10:color={RED}:t=fill,"
          f"drawtext=fontfile={FONT_M}:textfile={esc(ts)}:fontcolor={INK}:fontsize=60:"
          f"x=(w-text_w)/2:y=h/2+110:expansion=none:alpha='{fade}'")
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={CREAM}:s={W}x{H}:d={D}:r={FPS}",
         "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", "-r", str(FPS), out])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", required=True)
    ap.add_argument("--out", default="outputs/clips")
    args = ap.parse_args()
    pkg = pipeline.load_package(args.package)
    W, H = pkg["salida"]["resolucion"]; FPS = pkg["salida"].get("fps", 30)
    tmp = "/tmp/marli_cards"; os.makedirs(tmp, exist_ok=True)
    os.makedirs(args.out, exist_ok=True)
    made = 0
    for s in pipeline.iter_segments(pkg):
        uid = s["uid"]; out = os.path.join(args.out, f"{uid}.mp4")
        if s["formato"] == "kinetic_text":
            kinetic(s["seg"], uid, W, H, FPS, out, tmp); made += 1; print("  kinetic_text", uid)
        elif s["formato"] == "stat_reveal":
            stat(s["seg"], uid, W, H, FPS, out, tmp); made += 1; print("  stat_reveal", uid)
    print(f"Cards construidas: {made}")


if __name__ == "__main__":
    main()
