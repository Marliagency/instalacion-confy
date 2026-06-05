#!/usr/bin/env python3
"""
montage.py — Montador de pieza dirigido por el PAQUETE (project-aware).

Generaliza el montaje estilo QYRO: por cada segmento toma su clip
(projects/<slug>/outputs/clips/<uid>.mp4), superpone su captura real
(`captura`, assets/screenshots/) como inserto de móvil (marco + sombra, slide-in),
quema el copy en MAYÚSCULAS, encadena con transiciones dinámicas, añade una
tarjeta de cierre de marca con flash de las capturas, y mezcla la música.

Lo usa studio.py en la fase de montaje cuando la pieza usa insertos de captura
(t2v / screenshot_insert). Para piezas "clásicas" sin captura, studio usa assemble_pkg.

Lienzo y colores salen de brand.json. Todo local (sin GPU).
"""
import os, subprocess, sys

FONT_B  = "assets/fonts/Inter-Bold.ttf"
FONT_SB = "assets/fonts/Inter-SemiBold.ttf"
TMP = "/tmp/studio_montage"
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


def _hex(c, default):
    c = (c or default).lstrip("#")
    return "0x" + c


def copy_drawtext(idx, text, accent, W, H):
    tf = os.path.join(TMP, f"copy{idx}.txt"); open(tf, "w").write((text or "").upper())
    a_in = 0.5; alpha = f"if(lt(t,{a_in}),t/{a_in},1)"
    ty = int(H * 0.82); barw = 150
    return (f"drawbox=x=(iw-{barw})/2:y={ty-46}:w={barw}:h=8:color={accent}@0.95:t=fill:enable='gt(t,0.35)',"
            f"drawtext=fontfile={FONT_B}:textfile={esc(tf)}:fontcolor=white:fontsize=66:line_spacing=8:"
            f"x=(w-text_w)/2:y={ty}:box=1:boxcolor=black@0.45:boxborderw=30:expansion=none:alpha='{alpha}'")


def build_clip(i, clip, shot, copy, side, accent, W, H, FPS, out):
    D = dur(clip)
    base = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS},format=yuv420p")
    if shot and os.path.isfile(shot):
        ch = int(H * 0.62); margin = 56; t_in = 1.6
        if side == "left":
            xoff = "-w"; xt = f"{margin}"
            xexpr = f"if(lt(t,{t_in}),{xoff},if(lt(t,{t_in+0.45}),{xoff}+({margin}-({xoff}))*((t-{t_in})/0.45),{xt}))"
        else:
            xoff = "W"; xt = f"W-w-{margin}"
            xexpr = f"if(lt(t,{t_in}),{xoff},if(lt(t,{t_in+0.45}),{xoff}-({xoff}-({xt}))*((t-{t_in})/0.45),{xt}))"
        yexpr = "(H-h)/2"
        fc = (f"[0:v]{base}[bg];"
              f"[1:v]scale=-2:{ch},pad=iw+20:ih+20:10:10:white,setsar=1,split=2[card][cardb];"
              f"[cardb]format=rgba,colorchannelmixer=rr=0:gg=0:bb=0:aa=0.32[sh];"
              f"[bg][sh]overlay=x='({xexpr})+16':y='({yexpr})+20':format=auto[b1];"
              f"[b1][card]overlay=x='{xexpr}':y='{yexpr}':format=auto[b2];"
              f"[b2]{copy_drawtext(i, copy, accent, W, H)}[v]")
        run(["ffmpeg", "-y", "-i", clip, "-loop", "1", "-t", f"{D:.3f}", "-i", shot,
             "-filter_complex", fc, "-map", "[v]", "-an", "-r", str(FPS),
             "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", out])
    else:
        fc = f"[0:v]{base},{copy_drawtext(i, copy, accent, W, H)}[v]"
        run(["ffmpeg", "-y", "-i", clip, "-filter_complex", fc, "-map", "[v]", "-an", "-r", str(FPS),
             "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", out])
    return out, dur(out)


def build_closing(out, shots, nombre, tagline, accent, bg, W, H, FPS, seconds=3.6):
    flash_t = 0.22; parts = []
    for k, s in enumerate(shots):
        seg = os.path.join(TMP, f"flash{k}.mp4")
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS},format=yuv420p,eq=brightness=0.04")
        run(["ffmpeg", "-y", "-loop", "1", "-t", f"{flash_t:.3f}", "-i", s, "-vf", vf, "-r", str(FPS),
             "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", seg])
        parts.append(seg)
    logo = os.path.join(TMP, "logo.mp4")
    tag = os.path.join(TMP, "tag.txt"); open(tag, "w").write((tagline or "").upper())
    fin = os.path.join(TMP, "fin.txt"); open(fin, "w").write((nombre or "").upper())
    cd = max(1.5, seconds - len(shots) * flash_t)
    fade = f"if(lt(t,0.4),t/0.4,if(gt(t,{cd-0.5}),max(0\\,({cd}-t)/0.5),1))"
    vf = (f"format=yuv420p,fps={FPS},"
          f"drawtext=fontfile={FONT_B}:textfile={esc(fin)}:fontcolor=white:fontsize=210:expansion=none:"
          f"x=(w-text_w)/2:y={int(H*0.36)}:alpha='{fade}',"
          f"drawbox=x=(iw-200)/2:y={int(H*0.36)+250}:w=200:h=10:color={accent}@0.95:t=fill:enable='gt(t,0.4)',"
          f"drawtext=fontfile={FONT_SB}:textfile={esc(tag)}:fontcolor=white:fontsize=46:expansion=none:"
          f"x=(w-text_w)/2:y={int(H*0.36)+300}:alpha='{fade}'")
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={bg}:s={W}x{H}:d={cd:.3f}:r={FPS}", "-vf", vf,
         "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", logo])
    parts.append(logo)
    lst = os.path.join(TMP, "closing.txt")
    open(lst, "w").write("".join(f"file '{os.path.abspath(p)}'\n" for p in parts))
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c:v", "libx264", "-crf", "18",
         "-pix_fmt", "yuv420p", "-r", str(FPS), out])
    return out, dur(out)


def _offsets(durs, T):
    offs, t = [], 0.0
    for d in durs:
        offs.append(max(0.0, t)); t += d - T
    return offs


def build_audio(voice_jobs, music, total_s, out):
    """Mezcla música (con ducking bajo la voz) + voces en off colocadas por offset."""
    if not voice_jobs and not (music and os.path.isfile(music)):
        return None
    inputs, fc, labels, idx = [], [], [], 0
    if music and os.path.isfile(music):
        inputs += ["-i", music]
        gain = "0.55"
        for _p, off, vd in voice_jobs:                 # baja a 0.18 durante cada voz
            gain = f"({gain})*(1-0.72*between(t,{off:.3f},{off+vd:.3f}))"
        fc.append(f"[{idx}:a]volume=eval=frame:volume='{gain}',afade=t=in:st=0:d=0.8,"
                  f"afade=t=out:st={max(0,total_s-1.5):.2f}:d=1.5,atrim=0:{total_s:.2f}[m]")
        labels.append("[m]"); idx += 1
    for p, off, _vd in voice_jobs:
        inputs += ["-i", p]
        fc.append(f"[{idx}:a]adelay={int(off*1000)}|{int(off*1000)},volume=1.35[v{idx}]")
        labels.append(f"[v{idx}]"); idx += 1
    fc.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0,alimiter=limit=0.95[a]")
    run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(fc), "-map", "[a]",
         "-c:a", "aac", "-b:a", "192k", out])
    return out


def build(slug, brand, piece, clips_dir, screenshots_dir, music, out_path, voice_dir=None, T=0.25):
    """Monta la pieza con insertos de captura + voz en off + música. Devuelve out_path."""
    os.makedirs(TMP, exist_ok=True); os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    pal = brand["marca"].get("paleta", {})
    accent = _hex(pal.get("primario"), "E24B4A"); bg = _hex(pal.get("fondo"), "0B1220")
    res = brand["salida"].get("resolucion", [1080, 1920]); W, H = res[0], res[1]
    FPS = brand["salida"].get("fps", 30)
    nombre = brand["marca"].get("nombre", slug); tagline = brand["marca"].get("tagline", "")

    segs, durs, used_shots = [], [], []
    for i, seg in enumerate(piece["segmentos"]):
        uid = f"{piece['id']}__{seg['id']}"
        clip = os.path.join(clips_dir, f"{uid}.mp4")
        if not os.path.isfile(clip):
            sys.exit(f"Falta el clip {clip} (genera los clips antes del montaje).")
        cap = seg.get("captura")
        shot = os.path.join(screenshots_dir, cap) if cap else None
        if shot and os.path.isfile(shot):
            used_shots.append(shot)
        side = "right" if i % 2 == 0 else "left"
        o, d = build_clip(i, clip, shot, seg.get("texto_pantalla"), side, accent, W, H, FPS,
                          os.path.join(TMP, f"seg{i}.mp4"))
        segs.append(o); durs.append(d)
        print(f"  montaje seg {i+1}: {uid}{' +inserto' if shot else ''} ({d:.1f}s)", flush=True)
    # cierre
    co, cd = build_closing(os.path.join(TMP, "closing.mp4"), used_shots or [], nombre, tagline,
                           accent, bg, W, H, FPS)
    segs.append(co); durs.append(cd); print(f"  cierre {nombre} ({cd:.1f}s)", flush=True)

    inputs = []
    for s in segs: inputs += ["-i", s]
    fc = []; prev = "[0:v]"; total = durs[0]
    for i in range(1, len(segs)):
        off = max(0.0, total - T); lbl = f"[x{i}]"; tr = TRANS[(i - 1) % len(TRANS)]
        fc.append(f"{prev}[{i}:v]xfade=transition={tr}:duration={T}:offset={off:.3f}{lbl}")
        prev = lbl; total = total + durs[i] - T
    video = os.path.join(TMP, "video.mp4")
    run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(fc), "-map", prev,
         "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
         "-movflags", "+faststart", "-r", str(FPS), video])
    total_s = dur(video)
    # voces en off colocadas en su segmento (música baja bajo la voz)
    offs = _offsets(durs, T)
    voice_jobs = []
    if voice_dir:
        for i, seg in enumerate(piece["segmentos"]):
            uid = f"{piece['id']}__{seg['id']}"
            vp = os.path.join(voice_dir, f"{uid}_vo.mp3")
            if os.path.isfile(vp):
                voice_jobs.append((vp, offs[i] + 0.15, dur(vp)))
    audio = build_audio(voice_jobs, music, total_s, os.path.join(TMP, "audio.m4a"))
    if audio:
        run(["ffmpeg", "-y", "-i", video, "-i", audio, "-map", "0:v", "-map", "1:a",
             "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
             "-shortest", out_path])
    else:
        run(["ffmpeg", "-y", "-i", video, "-c", "copy", "-movflags", "+faststart", out_path])
    return out_path
