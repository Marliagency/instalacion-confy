#!/usr/bin/env python3
"""
compose_qyro.py — Monta el anuncio QYRO combinando formatos con su herramienta:
  - b-roll cinematográfico (WAN, clips ya renderizados)
  - motion graphics (Remotion): hook cinético, pantallas de app animadas, stat reveal, cierre
  - voz en off (ElevenLabs) + música (ElevenLabs)

Renderiza los segmentos Remotion con npx, normaliza el b-roll, encadena con
transiciones y mezcla el audio (voz colocada por segmento + música con ducking).
"""
import json, os, subprocess, sys

W, H, FPS = 1080, 1920, 30
T = 0.25
TMP = "/tmp/qyro_compose"
REM = "remotion"
CLIPS = "projects/qyro/outputs/clips_src"           # b-roll (copiado)
VOICE = "projects/qyro/outputs/voice"
MUSIC = "projects/qyro/assets/music/qyro_music.mp3"
OUT = "projects/qyro/outputs/anuncio_app.mp4"

# Timeline: cada herramienta para su formato
TIMELINE = [
    {"kind": "remotion", "comp": "KineticText", "props": {"lines": ["HOY", "NO SE", "NEGOCIA"], "accentLine": 2}},
    {"kind": "broll", "file": "outputs/qyro01_despertar.mp4", "vo": "anuncio_app__s1_vo.mp3"},
    {"kind": "remotion", "comp": "AppShowcase", "props": {"screenshot": "screenshots/01_habitos.png", "title": "TUS HÁBITOS, BAJO CONTROL", "badge": "RACHA 2 DÍAS"}},
    {"kind": "broll", "file": "outputs/qyro02_gimnasio.mp4", "vo": "anuncio_app__s2_vo.mp3"},
    {"kind": "remotion", "comp": "StatReveal", "props": {"value": 1, "prefix": "+", "suffix": " REP", "label": "EL PROGRESO NO DESCANSA"}},
    {"kind": "remotion", "comp": "AppShowcase", "props": {"screenshot": "screenshots/02_entrenos_progreso.png", "title": "TU PROGRESO, MEDIDO", "badge": "6 SUGERENCIAS"}},
    {"kind": "broll", "file": "outputs/qyro03_hidratacion.mp4", "vo": "anuncio_app__s3_vo.mp3"},
    {"kind": "remotion", "comp": "AppShowcase", "props": {"screenshot": "screenshots/03_nutricion_hoy.png", "title": "NUTRICIÓN CON IA", "badge": "FOTO CON IA"}},
    {"kind": "broll", "file": "outputs/qyro05_manifiesto.mp4", "vo": "anuncio_app__s5_vo.mp3"},
    {"kind": "remotion", "comp": "Closing", "props": {"brand": "QYRO", "tagline": "CONVIÉRTETE EN TU MEJOR VERSIÓN"}},
]


def run(cmd, **kw):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, **kw)
    if p.returncode != 0:
        sys.exit("ERROR:\n" + p.stdout[-2500:])
    return p.stdout


def dur(p):
    o = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nokey=1:noprint_wrappers=1", p], stdout=subprocess.PIPE, text=True).stdout.strip()
    return float(o)


def render_remotion(i, comp, props):
    out = os.path.abspath(os.path.join(TMP, f"seg{i}.mp4"))
    pf = os.path.join(TMP, f"props{i}.json"); json.dump(props, open(pf, "w"))
    print(f"  [remotion] {comp} …", flush=True)
    run(["npx", "remotion", "render", comp, out, f"--props={os.path.abspath(pf)}", "--log=error"], cwd=REM)
    return out


def normalize_broll(i, src):
    out = os.path.join(TMP, f"seg{i}.mp4")
    run(["ffmpeg", "-y", "-i", src, "-an",
         "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS},format=yuv420p",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", out])
    return out


def build_audio(voice_jobs, music, total_s, out):
    if not voice_jobs and not (music and os.path.isfile(music)):
        return None
    inputs, fc, labels, idx = [], [], [], 0
    if music and os.path.isfile(music):
        inputs += ["-i", music]; gain = "0.55"
        for _p, off, vd in voice_jobs:
            gain = f"({gain})*(1-0.72*between(t,{off:.3f},{off+vd:.3f}))"
        fc.append(f"[{idx}:a]volume=eval=frame:volume='{gain}',afade=t=in:st=0:d=0.8,"
                  f"afade=t=out:st={max(0,total_s-1.5):.2f}:d=1.5,atrim=0:{total_s:.2f}[m]")
        labels.append("[m]"); idx += 1
    for p, off, _vd in voice_jobs:
        inputs += ["-i", p]
        fc.append(f"[{idx}:a]adelay={int(off*1000)}|{int(off*1000)},volume=1.35[v{idx}]")
        labels.append(f"[v{idx}]"); idx += 1
    fc.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0,alimiter=limit=0.95[a]")
    run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(fc), "-map", "[a]", "-c:a", "aac", "-b:a", "192k", out])
    return out


def main():
    os.makedirs(TMP, exist_ok=True); os.makedirs(os.path.dirname(OUT), exist_ok=True)
    segs, durs, vo_idx = [], [], []
    for i, item in enumerate(TIMELINE):
        if item["kind"] == "remotion":
            o = render_remotion(i, item["comp"], item["props"])
        else:
            src = item["file"]
            if not os.path.isfile(src):
                sys.exit(f"Falta b-roll {src}")
            o = normalize_broll(i, src)
            print(f"  [b-roll] {os.path.basename(src)}", flush=True)
        d = dur(o); segs.append(o); durs.append(d)
        vo_idx.append(item.get("vo"))

    # transiciones dinámicas
    TR = ["slideleft", "wiperight", "slideup", "smoothleft", "slideright", "wipeleft"]
    inputs = []
    for s in segs: inputs += ["-i", s]
    fc = []; prev = "[0:v]"; total = durs[0]
    for i in range(1, len(segs)):
        off = max(0.0, total - T); lbl = f"[x{i}]"; tr = TR[(i - 1) % len(TR)]
        fc.append(f"{prev}[{i}:v]xfade=transition={tr}:duration={T}:offset={off:.3f}{lbl}")
        prev = lbl; total = total + durs[i] - T
    video = os.path.join(TMP, "video.mp4")
    run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(fc), "-map", prev,
         "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
         "-movflags", "+faststart", "-r", str(FPS), video])
    total_s = dur(video)

    # offsets de cada segmento (para colocar la voz)
    offs, t = [], 0.0
    for d in durs:
        offs.append(max(0.0, t)); t += d - T
    voice_jobs = []
    for i, vo in enumerate(vo_idx):
        if vo:
            vp = os.path.join(VOICE, vo)
            if os.path.isfile(vp):
                voice_jobs.append((vp, offs[i] + 0.2, dur(vp)))
    audio = build_audio(voice_jobs, MUSIC, total_s, os.path.join(TMP, "audio.m4a"))
    if audio:
        run(["ffmpeg", "-y", "-i", video, "-i", audio, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
             "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", OUT])
    else:
        run(["ffmpeg", "-y", "-i", video, "-c", "copy", OUT])
    print(f"\nFINAL -> {OUT}  ({dur(OUT):.1f}s)")


if __name__ == "__main__":
    main()
