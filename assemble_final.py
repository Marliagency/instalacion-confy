#!/usr/bin/env python3
"""
assemble_final.py — Montaje final del vídeo de marca de Marli ("Un día con Li").

Toma los clips WAN i2v (outputs/<id>.mp4) + los textos de cada escena
(batch_prompts.json), y produce un MP4 9:16 premium con la identidad de Marli:
lower-third con tipografía Inter, barra de acento en rojo Marli, transiciones
crossfade, tarjeta de cierre de marca y colchón ambiental.

    python3 assemble_final.py --out outputs/marli_final.mp4
"""
import argparse, json, os, subprocess, sys

# --- Identidad visual Marli ---
RED      = "0xE24B4A"   # rojo Marli
CREAM    = "0xFAF6F1"   # fondo crema
INK      = "0x2C2C2C"   # negro suave
MUTED    = "0x6B6B6B"   # gris medio
SCRIM    = "0x141210"   # casi negro para el lower-third
FONT_B   = "assets/fonts/Inter-Bold.ttf"
FONT_SB  = "assets/fonts/Inter-SemiBold.ttf"
FONT_M   = "assets/fonts/Inter-Medium.ttf"
W, H, FPS = 1080, 1920, 30
T = 0.5  # crossfade

def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode != 0:
        sys.exit("ERROR ffmpeg:\n" + p.stdout[-2500:])
    return p.stdout

def dur(path):
    o = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
                        "-of","default=nokey=1:noprint_wrappers=1", path],
                       stdout=subprocess.PIPE, text=True).stdout.strip()
    return float(o)

def esc_tf(path):  # ruta para textfile= en filtros
    return path.replace("\\","/").replace(":","\\:")

def caption_clip(src, text, out, tmpdir, idx):
    """Normaliza el clip a 9:16 y le quema el lower-third de marca con fade."""
    D = dur(src)
    tf = os.path.join(tmpdir, f"cap{idx}.txt")
    open(tf, "w").write((text or "").upper())   # R3.2: texto SIEMPRE en mayúsculas
    a_in, a_out = 0.45, 0.55  # fade in/out del texto
    # alpha del texto en función del tiempo del clip
    alpha = (f"if(lt(t,{a_in}),t/{a_in},"
             f"if(gt(t,{D-a_out}),max(0\\,({D}-t)/{a_out}),1))")
    show = f"between(t,0.25,{D-0.25})"   # barra de acento visible durante la frase
    ty = int(H*0.70)
    vf = (
        f"scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H},setsar=1,fps={FPS},format=yuv420p,"
        # barra de acento roja sobre el texto (iw = ancho del vídeo en drawbox)
        f"drawbox=x=(iw-150)/2:y={ty-46}:w=150:h=7:color={RED}@0.95:t=fill:enable='{show}',"
        # texto del lower-third con pastilla oscura para legibilidad
        f"drawtext=fontfile={FONT_SB}:textfile={esc_tf(tf)}:fontcolor=white:fontsize=62:"
        f"line_spacing=10:x=(w-text_w)/2:y={ty}:box=1:boxcolor={SCRIM}@0.55:boxborderw=34:"
        f"expansion=none:alpha='{alpha}'"
    )
    run(["ffmpeg","-y","-i",src,"-vf",vf,"-an","-r",str(FPS),
         "-c:v","libx264","-preset","medium","-crf","18","-pix_fmt","yuv420p", out])
    return out

def outro_card(out, tmpdir, seconds=3.2):
    """Tarjeta de cierre: fondo crema, wordmark 'marli' rojo, tagline y CTA."""
    tag = os.path.join(tmpdir,"tag.txt");  open(tag,"w").write("IA PARA PSICÓLOGOS")
    cta = os.path.join(tmpdir,"cta.txt");  open(cta,"w").write("PAGO ÚNICO · SE QUEDA CONTIGO PARA SIEMPRE")
    fin = os.path.join(tmpdir,"fin.txt");  open(fin,"w").write("marli")   # wordmark = logo (se mantiene)
    fade = (f"if(lt(t,0.5),t/0.5,if(gt(t,{seconds-0.6}),max(0\\,({seconds}-t)/0.6),1))")
    vf = (
        f"format=yuv420p,fps={FPS},"
        f"drawtext=fontfile={FONT_B}:textfile={esc_tf(fin)}:fontcolor={RED}:fontsize=210:"
        f"expansion=none:x=(w-text_w)/2:y={int(H*0.34)}:alpha='{fade}',"
        f"drawbox=x=(iw-180)/2:y={int(H*0.34)+250}:w=180:h=9:color={RED}@0.9:t=fill:enable='gt(t,0.4)',"
        f"drawtext=fontfile={FONT_M}:textfile={esc_tf(tag)}:fontcolor={INK}:fontsize=58:"
        f"expansion=none:x=(w-text_w)/2:y={int(H*0.34)+300}:alpha='{fade}',"
        f"drawtext=fontfile={FONT_M}:textfile={esc_tf(cta)}:fontcolor={MUTED}:fontsize=36:"
        f"expansion=none:x=(w-text_w)/2:y={int(H*0.34)+390}:alpha='{fade}'"
    )
    run(["ffmpeg","-y","-f","lavfi","-i",f"color=c={CREAM}:s={W}x{H}:d={seconds}:r={FPS}",
         "-vf",vf,"-c:v","libx264","-preset","medium","-crf","18","-pix_fmt","yuv420p", out])
    return out, seconds

def xfade_concat(clips, durs, out, music):
    inputs=[]
    for c in clips: inputs += ["-i", c]
    inputs += ["-i", music]
    fc=[]
    # normalizadas ya; construir cadena xfade
    prev="[0:v]"; total=durs[0]
    for i in range(1,len(clips)):
        off=max(0.0, total - T)
        lbl=f"[x{i}]"
        fc.append(f"{prev}[{i}:v]xfade=transition=fade:duration={T}:offset={off:.3f}{lbl}")
        prev=lbl; total = total + durs[i] - T
    vlast=prev
    midx=len(clips)
    fc.append(f"[{midx}:a]atrim=0:{total:.3f},afade=t=out:st={max(0,total-2):.3f}:d=2[a]")
    fg=";".join(fc)
    run(["ffmpeg","-y",*inputs,"-filter_complex",fg,"-map",vlast,"-map","[a]",
         "-c:v","libx264","-preset","slow","-crf","19","-pix_fmt","yuv420p",
         "-c:a","aac","-b:a","192k","-movflags","+faststart","-r",str(FPS), out])
    return total

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--prompts",default="batch_prompts.json")
    ap.add_argument("--clips-dir",default="outputs")
    ap.add_argument("--music",default="assets/bed.wav")
    ap.add_argument("--out",default="outputs/marli_final.mp4")
    args=ap.parse_args()
    items=json.load(open(args.prompts))
    tmp="/tmp/marli_build"; os.makedirs(tmp,exist_ok=True)
    cap_clips=[]; durs=[]
    for i,it in enumerate(items):
        src=os.path.join(args.clips_dir, f"{it['id']}.mp4")
        if not os.path.isfile(src):
            sys.exit(f"falta el clip {src}")
        out=os.path.join(tmp,f"cap_{it['id']}.mp4")
        caption_clip(src, it.get("texto",""), out, tmp, i)
        cap_clips.append(out); durs.append(dur(out))
        print(f"  caption {it['id']} ({durs[-1]:.2f}s)")
    oc, od = outro_card(os.path.join(tmp,"outro.mp4"), tmp)
    cap_clips.append(oc); durs.append(od)
    print("  outro card", f"{od:.2f}s")
    os.makedirs(os.path.dirname(os.path.abspath(args.out)),exist_ok=True)
    total=xfade_concat(cap_clips, durs, args.out, args.music)
    print(f"\nFINAL -> {args.out}  ({dur(args.out):.1f}s, {os.path.getsize(args.out)/1e6:.1f} MB)")

if __name__=="__main__":
    main()
