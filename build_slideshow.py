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

def build_one(images, out, W, H, FPS, total_s):
    n = len(images)
    per = max(1.5, total_s / n)
    frames = int(per * FPS)
    seg_filters, inputs = [], []
    for i, img in enumerate(images):
        inputs += ["-loop", "1", "-t", f"{per:.2f}", "-i", img]
        # Ken Burns: zoom lento + encuadre 9:16
        zdir = 1 if i % 2 == 0 else -1
        z = ("zoom+0.0010" if zdir == 1 else "if(lte(zoom,1.0),1.18,zoom-0.0010)")
        seg_filters.append(
            f"[{i}:v]scale={W*2}:{H*2}:force_original_aspect_ratio=increase,crop={W*2}:{H*2},"
            f"zoompan=z='{z}':d={frames}:s={W}x{H}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':fps={FPS},"
            f"setsar=1,format=yuv420p[v{i}]"
        )
    # crossfade encadenado entre slides
    T = 0.4
    chain = seg_filters[:]
    prev = "[v0]"; total = per
    for i in range(1, n):
        off = max(0.0, total - T)
        lbl = f"[x{i}]"
        chain.append(f"{prev}[v{i}]xfade=transition=fade:duration={T}:offset={off:.3f}{lbl}")
        prev = lbl; total = total + per - T
    fg = ";".join(chain)
    run(["ffmpeg","-y",*inputs,"-filter_complex",fg,"-map",prev,
         "-c:v","libx264","-preset","medium","-crf","19","-pix_fmt","yuv420p","-r",str(FPS),out])

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
        out = os.path.join(args.out, f"{seg['id']}.mp4")
        build_one(imgs, out, W, H, FPS, seg.get("duracion_s", 6))
        print(f"  slideshow {seg['id']} -> {out}"); made += 1
    print(f"Slideshows construidos: {made}")

if __name__ == "__main__":
    main()
