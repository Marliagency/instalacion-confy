#!/usr/bin/env python3
"""
build_qyro_montage.py — Montaje final del anuncio QYRO (estilo Nike).

Toma los 5 clips IA (outputs/qyro0X_*.mp4, 9:16) y superpone las CAPTURAS REALES
de la app (assets/qyro/*.png) como insertos de móvil (tarjeta con marco blanco +
sombra, entrando con un slide), añade el copy en MAYÚSCULAS animado, encadena los
clips con transiciones dinámicas, añade una tarjeta de cierre QYRO con flash de
las 4 pantallas, y mezcla la música.

    python3 build_qyro_montage.py --music outputs/qyro_music.mp3 --out outputs/qyro_montage.mp4

Lienzo 1080x1920, 30 fps. Todo local (sin GPU).
"""
import argparse, os, subprocess, sys

W, H, FPS = 1080, 1920, 30
FONT_B  = "assets/fonts/Inter-Bold.ttf"
FONT_SB = "assets/fonts/Inter-SemiBold.ttf"
BLUE    = "0x2563EB"   # azul QYRO
INK     = "0x0B1220"   # fondo oscuro cierre
TMP = "/tmp/qyro_mix"

# (clip, captura, copy MAYÚSCULAS, t de entrada del inserto, lado)
CLIPS = [
    ("outputs/qyro01_despertar.mp4",   "assets/qyro/01_habitos.png",
     "HOY NO SE NEGOCIA.",            2.0, "right"),
    ("outputs/qyro02_gimnasio.mp4",    "assets/qyro/02_entrenos_progreso.png",
     "EL PROGRESO NO DESCANSA.",      1.6, "right"),
    ("outputs/qyro03_hidratacion.mp4", "assets/qyro/03_nutricion_hoy.png",
     "CUIDA LA MÁQUINA.",             1.5, "left"),
    ("outputs/qyro04_nutricion.mp4",   "assets/qyro/04_nutricion_alimentos.png",
     "COME PARA GANAR.",              1.7, "right"),
    ("outputs/qyro05_manifiesto.mp4",  None,
     "CONVIÉRTETE EN TU MEJOR VERSIÓN.", None, None),
]
SHOTS = ["assets/qyro/01_habitos.png", "assets/qyro/02_entrenos_progreso.png",
         "assets/qyro/03_nutricion_hoy.png", "assets/qyro/04_nutricion_alimentos.png"]
TRANS = ["slideleft", "wiperight", "slideup", "smoothleft", "slideright"]


def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode != 0:
        sys.exit("ERROR ffmpeg:\n" + p.stdout[-2800:])
    return p.stdout


def dur(path):
    o = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nokey=1:noprint_wrappers=1", path],
                       stdout=subprocess.PIPE, text=True).stdout.strip()
    return float(o)


def esc(p):
    return p.replace("\\", "/").replace(":", "\\:")


def card_h():
    return int(H * 0.62)   # alto de la tarjeta-inserto


def base_vf():
    return (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},setsar=1,fps={FPS},format=yuv420p")


def copy_drawtext(idx, text, D):
    """drawtext del copy (mayúsculas, Inter-Bold) + barra de acento azul, con fade."""
    tf = os.path.join(TMP, f"copy{idx}.txt"); open(tf, "w").write(text.upper())
    a_in = 0.5
    alpha = f"if(lt(t,{a_in}),t/{a_in},1)"
    ty = int(H * 0.82)
    barw = 150
    return (
        f"drawbox=x=(iw-{barw})/2:y={ty-46}:w={barw}:h=8:color={BLUE}@0.95:t=fill:enable='gt(t,0.35)',"
        f"drawtext=fontfile={FONT_B}:textfile={esc(tf)}:fontcolor=white:fontsize=66:"
        f"line_spacing=8:x=(w-text_w)/2:y={ty}:box=1:boxcolor=black@0.45:boxborderw=30:"
        f"expansion=none:alpha='{alpha}'"
    )


def build_clip(i, clip, shot, copy, t_in, side, out):
    """Un clip: base 9:16 + inserto de captura (slide-in) + copy."""
    D = dur(clip)
    cw_target = "iw*0"  # placeholder
    if shot and os.path.isfile(shot):
        ch = card_h()
        # tarjeta = captura escalada a ch de alto + marco blanco (pad 10px) + sombra
        margin = 56
        # posición destino X según lado; el ancho real se resuelve por aspecto en runtime,
        # así que estimamos card_w por el aspecto típico de captura (~0.563) y ajustamos en overlay.
        # Usamos overlay con W (ancho del main) y w (ancho del overlay) en la expresión.
        if side == "left":
            xt = f"{margin}"; xoff = f"-w"          # entra desde la izquierda
            xexpr = (f"if(lt(t,{t_in}),{xoff},"
                     f"if(lt(t,{t_in+0.45}),{xoff}+({margin}-({xoff}))*((t-{t_in})/0.45),{xt}))")
        else:
            xt = f"W-w-{margin}"; xoff = "W"          # entra desde la derecha
            xexpr = (f"if(lt(t,{t_in}),{xoff},"
                     f"if(lt(t,{t_in+0.45}),{xoff}-({xoff}-({xt}))*((t-{t_in})/0.45),{xt}))")
        yexpr = f"(H-h)/2"
        # sombra: caja negra desplazada bajo la tarjeta (se dibuja en base por drawbox dinámico)
        # más simple y robusto: overlay de la tarjeta con marco blanco; la sombra se simula
        # con un segundo overlay negro a 35% desplazado (+14,+18).
        fc = (
            f"[0:v]{base_vf()}[bg];"
            f"[1:v]scale=-2:{ch},pad=iw+20:ih+20:10:10:white,setsar=1,split=2[card][cardb];"
            f"[cardb]format=rgba,colorchannelmixer=rr=0:gg=0:bb=0:aa=0.32[sh];"
            f"[bg][sh]overlay=x='({xexpr})+16':y='({yexpr})+20':format=auto[b1];"
            f"[b1][card]overlay=x='{xexpr}':y='{yexpr}':format=auto[b2];"
            f"[b2]{copy_drawtext(i, copy, D)}[v]"
        )
        run(["ffmpeg", "-y", "-i", clip, "-loop", "1", "-t", f"{D:.3f}", "-i", shot,
             "-filter_complex", fc, "-map", "[v]", "-an", "-r", str(FPS),
             "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", out])
    else:
        fc = f"[0:v]{base_vf()},{copy_drawtext(i, copy, D)}[v]"
        run(["ffmpeg", "-y", "-i", clip, "-filter_complex", fc, "-map", "[v]", "-an",
             "-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "18",
             "-pix_fmt", "yuv420p", out])
    return out, dur(out)


def build_closing(out, seconds=3.6):
    """Cierre: flash veloz de las 4 capturas (0.2s c/u) -> tarjeta QYRO."""
    flash_t = 0.22
    parts = []
    # flashes
    for k, s in enumerate(SHOTS):
        seg = os.path.join(TMP, f"flash{k}.mp4")
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
              f"setsar=1,fps={FPS},format=yuv420p,eq=brightness=0.04")
        run(["ffmpeg", "-y", "-loop", "1", "-t", f"{flash_t:.3f}", "-i", s, "-vf", vf,
             "-r", str(FPS), "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", seg])
        parts.append(seg)
    # tarjeta logo
    logo = os.path.join(TMP, "logo.mp4")
    tag = os.path.join(TMP, "tag.txt"); open(tag, "w").write("CONVIÉRTETE EN TU MEJOR VERSIÓN")
    fin = os.path.join(TMP, "fin.txt"); open(fin, "w").write("QYRO")
    cd = seconds - len(SHOTS) * flash_t
    fade = f"if(lt(t,0.4),t/0.4,if(gt(t,{cd-0.5}),max(0\\,({cd}-t)/0.5),1))"
    vf = (f"format=yuv420p,fps={FPS},"
          f"drawtext=fontfile={FONT_B}:textfile={esc(fin)}:fontcolor=white:fontsize=240:"
          f"expansion=none:x=(w-text_w)/2:y={int(H*0.36)}:alpha='{fade}',"
          f"drawbox=x=(iw-200)/2:y={int(H*0.36)+280}:w=200:h=10:color={BLUE}@0.95:t=fill:enable='gt(t,0.4)',"
          f"drawtext=fontfile={FONT_SB}:textfile={esc(tag)}:fontcolor=white:fontsize=46:"
          f"expansion=none:x=(w-text_w)/2:y={int(H*0.36)+330}:alpha='{fade}'")
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={INK}:s={W}x{H}:d={cd:.3f}:r={FPS}",
         "-vf", vf, "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", logo])
    parts.append(logo)
    # concat (hard cuts) de los flashes + logo
    lst = os.path.join(TMP, "closing.txt")
    open(lst, "w").write("".join(f"file '{os.path.abspath(p)}'\n" for p in parts))
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst,
         "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS), out])
    return out, dur(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--music", default=None)
    ap.add_argument("--out", default="outputs/qyro_montage.mp4")
    ap.add_argument("--T", type=float, default=0.25, help="duración de transición")
    args = ap.parse_args()
    os.makedirs(TMP, exist_ok=True); os.makedirs("outputs", exist_ok=True)

    # comprobar capturas
    missing = [c[1] for c in CLIPS if c[1] and not os.path.isfile(c[1])] + \
              [s for s in SHOTS if not os.path.isfile(s)]
    if missing:
        sys.exit("Faltan capturas (súbelas a assets/qyro/):\n  " + "\n  ".join(sorted(set(missing))))

    segs, durs = [], []
    for i, (clip, shot, copy, t_in, side) in enumerate(CLIPS):
        out = os.path.join(TMP, f"seg{i}.mp4")
        o, d = build_clip(i, clip, shot, copy, t_in, side, out)
        segs.append(o); durs.append(d); print(f"  clip {i+1}: {os.path.basename(clip)} ({d:.1f}s)", flush=True)
    co, cd = build_closing(os.path.join(TMP, "closing_final.mp4"))
    segs.append(co); durs.append(cd); print(f"  cierre QYRO ({cd:.1f}s)", flush=True)

    # concat con transiciones dinámicas (xfade)
    T = args.T
    inputs = []
    for s in segs: inputs += ["-i", s]
    fc = []; prev = "[0:v]"; total = durs[0]
    for i in range(1, len(segs)):
        off = max(0.0, total - T); lbl = f"[x{i}]"
        tr = TRANS[(i - 1) % len(TRANS)]
        fc.append(f"{prev}[{i}:v]xfade=transition={tr}:duration={T}:offset={off:.3f}{lbl}")
        prev = lbl; total = total + durs[i] - T
    video = os.path.join(TMP, "video.mp4")
    run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(fc), "-map", prev,
         "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
         "-movflags", "+faststart", "-r", str(FPS), video])
    total_s = dur(video)

    if args.music and os.path.isfile(args.music):
        run(["ffmpeg", "-y", "-i", video, "-i", args.music,
             "-filter_complex",
             f"[1:a]atrim=0:{total_s:.3f},afade=t=in:st=0:d=0.8,"
             f"afade=t=out:st={max(0,total_s-1.5):.2f}:d=1.5,volume=0.9[a]",
             "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart", "-shortest", args.out])
    else:
        run(["ffmpeg", "-y", "-i", video, "-c", "copy", "-movflags", "+faststart", args.out])
    print(f"\nFINAL -> {args.out}  ({dur(args.out):.1f}s)")


if __name__ == "__main__":
    main()
