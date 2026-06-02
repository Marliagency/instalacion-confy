#!/usr/bin/env python3
"""
build_slideshow.py — Construye el clip de un segmento de formato 'slideshow'
a partir de sus N imágenes (Ken Burns + crossfades). LOCAL, sin GPU.

Lo usa la Sesión B para los segmentos slideshow; produce outputs/clips/<id>.mp4
con la misma resolución/fps que el resto de clips, para que assemble_final.py
los una igual que los clips WAN.

    python3 build_slideshow.py --package examples/marli_ad01.json \
        --images outputs/images --out outputs/clips
"""
import argparse, os, subprocess, sys
import pipeline

def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode != 0:
        sys.exit("ERROR ffmpeg:\n" + p.stdout[-2000:])

FONT_B = "assets/fonts/Inter-Bold.ttf"
RED, SCRIM = "0xE24B4A", "0x141210"

def build_one(images, out, W, H, FPS, total_s, captions=None, tmpdir="/tmp/marli_slide"):
    os.makedirs(tmpdir, exist_ok=True)
    captions = captions or [None] * len(images)
    n = len(images)
    per = max(1.5, total_s / n)
    frames = int(per * FPS)
    ty = int(H * 0.72)
    # 1) cada still -> subclip Ken Burns por separado (evita la multiplicación de frames
    #    de zoompan al recibir un input multi-frame).
    subs = []
    for i, img in enumerate(images):
        z = f"min(zoom+{0.14/frames:.6f},1.14)"   # zoom-in lento y uniforme
        vf = (f"scale={W*2}:{H*2}:force_original_aspect_ratio=increase,crop={W*2}:{H*2},"
              f"zoompan=z='{z}':d={frames}:s={W}x{H}:fps={FPS}:"
              f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)',setsar=1,format=yuv420p")
        if captions[i]:
            tf = os.path.join(tmpdir, f"cap{i}.txt"); open(tf, "w").write(captions[i])
            tfp = tf.replace(":", "\\:")
            vf += (f",drawbox=x=(iw-130)/2:y={ty-42}:w=130:h=7:color={RED}@0.95:t=fill"
                   f",drawtext=fontfile={FONT_B}:textfile={tfp}:fontcolor=white:fontsize=64:"
                   f"x=(w-text_w)/2:y={ty}:box=1:boxcolor={SCRIM}@0.55:boxborderw=30:expansion=none")
        sub = os.path.join(tmpdir, f"sub{i}.mp4")
        run(["ffmpeg", "-y", "-loop", "1", "-i", img, "-vf", vf, "-t", f"{per:.2f}",
             "-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "19",
             "-pix_fmt", "yuv420p", sub])
        subs.append(sub)
    # 2) crossfade encadenado entre subclips
    T = 0.4
    inputs = []
    for s in subs: inputs += ["-i", s]
    chain = []; prev = "[0:v]"; total = per
    for i in range(1, n):
        off = max(0.0, total - T); lbl = f"[x{i}]"
        chain.append(f"{prev}[{i}:v]xfade=transition=fade:duration={T}:offset={off:.3f}{lbl}")
        prev = lbl; total = total + per - T
    if n == 1:
        run(["ffmpeg", "-y", "-i", subs[0], "-c", "copy", out]); return
    run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(chain), "-map", prev,
         "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", "-r", str(FPS), out])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", required=True)
    ap.add_argument("--images", default="outputs/images")
    ap.add_argument("--out", default="outputs/clips")
    args = ap.parse_args()
    pkg = pipeline.load_package(args.package)
    W, H = pkg["salida"]["resolucion"]; FPS = pkg["salida"].get("fps", 30)
    os.makedirs(args.out, exist_ok=True)
    made = 0
    for s in pipeline.iter_segments(pkg):
        if s["formato"] != "slideshow":
            continue
        seg = s["seg"]; n = len(seg.get("imagenes", []))
        imgs = [os.path.join(args.images, f"{seg['id']}_{i}.png") for i in range(1, n+1)]
        missing = [p for p in imgs if not os.path.isfile(p)]
        if missing:
            print(f"  {seg['id']}: faltan imágenes {missing}"); continue
        caps = [im.get("texto") for im in seg.get("imagenes", [])]
        out = os.path.join(args.out, f"{seg['id']}.mp4")
        build_one(imgs, out, W, H, FPS, seg.get("duracion_s", 6), captions=caps)
        print(f"  slideshow {seg['id']} -> {out}"); made += 1
    print(f"Slideshows construidos: {made}")

if __name__ == "__main__":
    main()
