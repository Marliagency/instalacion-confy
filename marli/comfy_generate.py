#!/usr/bin/env python3
"""
comfy_generate.py — Orquestador de anuncios verticales de Marli.

De un config YAML (un anuncio entero de 30 s en 6 beats) a un MP4 9:16 final,
combinando los 4 formatos de Marli: CINEMATIC, UGC, TEXT_CARD y SLIDESHOW_5.

La generación de píxeles ocurre en ComfyUI (en el pod de RunPod); el montaje
(text cards, slideshow, concatenación y mezcla de audio) ocurre aquí con ffmpeg.

Dependencias: solo `pyyaml` (+ ffmpeg en el PATH). La comunicación con ComfyUI va
con la librería estándar (urllib), sin más pips.

Uso:
    export COMFY_HOST="http://<POD-IP>:8188"      # o usa --host
    python3 comfy_generate.py configs/marli_v2.yaml
    python3 comfy_generate.py configs/marli_v2.yaml --simular   # sin GPU (placeholders)

Salida:
    outputs/<name>/beat<n>_<type>_<id>.mp4   (+ .png intermedios)
    outputs/<name>.mp4                         (anuncio final de 30 s)

Ver PRODUCTION.md para el detalle de workflows, modelos y config.
"""

import argparse
import copy
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid

try:
    import yaml
except ImportError:
    raise SystemExit("Falta pyyaml. Instala con: pip install pyyaml")

HERE = os.path.dirname(os.path.abspath(__file__))
WORKFLOWS_DIR = os.path.join(HERE, "comfy_workflows")
FONTS_DIR = os.path.join(HERE, "fonts")
ASSETS_DIR = os.path.join(HERE, "assets")
OUT_ROOT = os.path.join(HERE, "outputs")

W, H = 1080, 1920  # 9:16 vertical

# --- §2.1 Estilo visual (sufijo de prompt) ---
STYLE_SUFFIX = {
    "editorial": ", premium editorial advertising style, soft cream tones, "
                 "Sony A7R look, shallow depth of field",
    "cinematic": ", cinematic, anamorphic lens, dramatic key light, film grain, "
                 "ARRI Alexa look",
    "handheld": ", handheld phone selfie, slight natural shake, iPhone front-camera aesthetic",
    "studio": ", clean studio backdrop, soft box lighting, product photography",
    "golden-hour": ", warm golden-hour window light, long soft shadows",
    "noir": ", low-key noir lighting, deep shadows, single hard key light",
}

# --- §2.2 Cámara ---
CAMERA_PHRASE = {
    "static": "",
    "slow-push-in": ", slow gentle cinematic push-in",
    "slow-orbit": ", smooth slow orbiting camera around subject",
    "dolly-left": ", smooth dolly to the left",
    "dolly-right": ", smooth dolly to the right",
    "handheld": ", slight natural handheld movement",
}

NEGATIVE_DEFAULT = "text, letters, logos, watermarks, distorted hands, blurry"

WORKFLOW_BY_TYPE = {
    "cinematic": "cinematic_wan22.json",
    "ugc": "ugc_wan22.json",
    "textcard": "image_flux_dev.json",
    "slideshow5": "image_flux_dev.json",  # una imagen por slide (prompts distintos)
}


# ===========================================================================
# ffmpeg helpers
# ===========================================================================
def run(cmd, check=True):
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if check and res.returncode != 0:
        raise RuntimeError("ffmpeg falló:\n" + res.stderr.decode("utf-8", "ignore")[-800:])
    return res


def _font(brand, clave, defecto):
    f = (brand.get("fonts") or {}).get(clave)
    if f and os.path.exists(os.path.join(HERE, f)):
        return os.path.join(HERE, f)
    if f and os.path.exists(f):
        return f
    # Respaldo: la fuente de marca o DejaVu.
    for cand in (os.path.join(FONTS_DIR, defecto),
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if os.path.exists(cand):
            return cand
    return None


def make_kenburns(still, dst, dur, fps):
    """Convierte una imagen fija en un clip con movimiento (zoom-in suave).
    Fallback de vídeo cuando no hay modelo Wan: imagen IA real + movimiento."""
    nframes = max(1, int(round(dur * fps)))
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
          f"scale={2 * W}:{2 * H},"
          f"zoompan=z='min(zoom+0.0012,1.18)':d={nframes}:"
          f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={fps},"
          f"setsar=1,format=yuv420p")
    run(["ffmpeg", "-y", "-i", still, "-vf", vf, "-t", f"{dur}", "-r", str(fps),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", dst])
    return dst


def overlay_li(clip_in, clip_out, cutout, placement, dur, fps):
    """Compone la mascota Li (PNG con alfa) sobre el clip, con un flote sutil.
    placement: hero | side | corner | center."""
    cfgp = {
        "hero":   (0.74, "W-w-W*0.03"),
        "side":   (0.58, "W-w-W*0.03"),
        "center": (0.80, "(W-w)/2"),
        "corner": (0.26, "W-w-W*0.06"),
    }.get(placement, (0.6, "W-w-W*0.04"))
    frac, x = cfgp
    ih = int(H * frac)
    if placement == "corner":
        y = f"H*0.60+8*sin(2*PI*t/3.5)"
    else:
        y = f"H-h+10*sin(2*PI*t/3.5)"          # anclado abajo, flote suave
    fc = (f"[1:v]scale=-1:{ih}:flags=lanczos[li];"
          f"[0:v][li]overlay=x={x}:y='{y}':format=auto[v]")
    run(["ffmpeg", "-y", "-i", clip_in, "-loop", "1", "-i", cutout,
         "-filter_complex", fc, "-map", "[v]", "-map", "0:a?",
         "-t", f"{dur}", "-r", str(fps),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-pix_fmt", "yuv420p", "-c:a", "copy", clip_out])
    return clip_out


def add_vo(clip_in, clip_out, vo_path, dur):
    """Sustituye el audio del beat por la locución (recortada/rellenada a dur)."""
    run(["ffmpeg", "-y", "-i", clip_in, "-i", vo_path,
         "-filter_complex", f"[1:a]apad,atrim=0:{dur},asetpts=PTS-STARTPTS[a]",
         "-map", "0:v:0", "-map", "[a]",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", clip_out])
    return clip_out


def normalize_clip(src, dst, dur, fps):
    """Lleva cualquier clip a 1080x1920, fps fijo, duración exacta y audio (silencio
    si no trae), para que la concatenación final sea perfecta."""
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
          f"setsar=1,fps={fps},format=yuv420p")
    cmd = ["ffmpeg", "-y", "-i", src,
           "-f", "lavfi", "-t", f"{dur}", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
           "-map", "0:v:0", "-map", "1:a:0", "-shortest",
           "-vf", vf, "-t", f"{dur}",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
           "-c:a", "aac", "-b:a", "128k", "-r", str(fps), dst]
    run(cmd)
    return dst


def has_audio(src):
    res = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a",
                          "-show_entries", "stream=index", "-of", "csv=p=0", src],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return bool(res.stdout.strip())


# ===========================================================================
# Cliente ComfyUI (urllib)
# ===========================================================================
# Cloudflare (proxy de RunPod) rechaza con 403 el User-Agent por defecto de urllib;
# hay que enviar uno de navegador.
_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


class Comfy:
    def __init__(self, host):
        self.host = host.rstrip("/")
        self.cid = str(uuid.uuid4())

    def _get(self, path, timeout=30):
        req = urllib.request.Request(self.host + path, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def queue(self, workflow):
        data = json.dumps({"prompt": workflow, "client_id": self.cid}).encode()
        req = urllib.request.Request(self.host + "/prompt", data=data,
                                     headers={"Content-Type": "application/json",
                                              "User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))["prompt_id"]

    def wait_download(self, prompt_id, dest, timeout=1200, poll=3):
        start = time.time()
        while True:
            if time.time() - start > timeout:
                raise TimeoutError(f"timeout esperando {prompt_id}")
            try:
                hist = self._get(f"/history/{prompt_id}")
            except Exception:
                time.sleep(poll); continue
            entry = hist.get(prompt_id)
            if entry:
                st = entry.get("status", {})
                if st.get("status_str") == "error":
                    raise RuntimeError(f"ComfyUI error en {prompt_id}")
                for node_out in entry.get("outputs", {}).values():
                    for key in ("images", "gifs", "videos"):
                        for it in node_out.get(key, []):
                            if it.get("filename"):
                                return self._download(it, dest)
                if st.get("completed"):
                    raise RuntimeError(f"{prompt_id} sin salida")
            time.sleep(poll)

    def _download(self, item, dest):
        params = urllib.parse.urlencode({"filename": item.get("filename", ""),
                                         "subfolder": item.get("subfolder", ""),
                                         "type": item.get("type", "output")})
        os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
        req = urllib.request.Request(self.host + "/view?" + params, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
            f.write(r.read())
        return dest


# ===========================================================================
# Parcheo de workflows (busca nodos por título/clase, como indica PRODUCTION.md §4)
# ===========================================================================
def load_workflow(name):
    path = os.path.join(WORKFLOWS_DIR, name)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _nodes(wf):
    for nid, node in wf.items():
        if isinstance(node, dict) and "class_type" in node:
            yield nid, node


def _title(node):
    return (node.get("_meta", {}).get("title") or "").lower()


def patch_workflow(wf, positive, negative, seed, frames=None, gw=W, gh=H):
    """Parchea prompt+/prompt-/seed/dimensiones/nº de frames sobre una copia."""
    wf = copy.deepcopy(wf)
    wf = {k: v for k, v in wf.items() if isinstance(v, dict) and "class_type" in v}

    pos_id = neg_id = None
    for nid, node in _nodes(wf):
        if "CLIPTextEncode" in node["class_type"]:
            t = _title(node)
            if "positive" in t or t in ("pos", "prompt"):
                pos_id = nid
            elif "negative" in t or t == "neg":
                neg_id = nid
    # Respaldo: primer/segundo CLIPTextEncode si no hay títulos.
    if pos_id is None:
        encs = [nid for nid, n in _nodes(wf) if "CLIPTextEncode" in n["class_type"]]
        if encs:
            pos_id = encs[0]
            if neg_id is None and len(encs) > 1:
                neg_id = encs[1]
    if pos_id:
        wf[pos_id]["inputs"]["text"] = positive
    if neg_id:
        wf[neg_id]["inputs"]["text"] = negative

    for nid, node in _nodes(wf):
        ins = node.get("inputs", {})
        ct = node["class_type"]
        # Semilla
        for k in ("seed", "noise_seed"):
            if k in ins and isinstance(ins[k], (int, float)):
                ins[k] = int(seed)
        # Dimensiones (cualquier nodo Empty*Latent*)
        if "Empty" in ct and "Latent" in ct:
            if "width" in ins:
                ins["width"] = int(gw)
            if "height" in ins:
                ins["height"] = int(gh)
            if frames is not None and "length" in ins:
                ins["length"] = int(frames)
    return wf


# ===========================================================================
# Construcción de prompts
# ===========================================================================
def build_prompt(base, style, camera, is_video):
    p = base.strip().rstrip(",")
    p += STYLE_SUFFIX.get(style, "")
    if is_video:
        p += CAMERA_PHRASE.get(camera, "")
    return p


def resolve(beat, cfg, clave, defecto=None):
    return beat.get(clave, cfg.get(clave, defecto))


def beat_seed(beat, cfg, idx):
    s = resolve(beat, cfg, "seed", 42)
    if isinstance(s, str) and s.lower() == "random":
        import random
        return random.randint(1, 2_147_483_646)
    return int(s) + idx  # desplaza por beat para que no salgan idénticos


# ===========================================================================
# Generación de píxeles (real o simulada)
# ===========================================================================
PALETTE = ["3a0a0a", "7a0c0c", "9a1b1b", "b5651d", "2b2b2b", "0e1b2b"]


def sim_image(dest, label, idx):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    color = PALETTE[idx % len(PALETTE)]
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0x{color}:s={W}x{H}",
         "-frames:v", "1", dest])
    return dest


def sim_video(dest, label, idx, dur, fps):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    color = PALETTE[idx % len(PALETTE)]
    # testsrc sutil sobre color de marca para que se note el movimiento.
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0x{color}:s={W}x{H}:d={dur}:r={fps}",
         "-vf", "format=yuv420p", "-t", f"{dur}", dest])
    return dest


def gen_image(comfy, simular, wf_name, positive, negative, seed, dest, label, idx,
              gw=W, gh=H):
    if simular:
        return sim_image(dest, label, idx)
    wf = patch_workflow(load_workflow(wf_name), positive, negative, seed, gw=gw, gh=gh)
    pid = comfy.queue(wf)
    return comfy.wait_download(pid, dest)


def gen_video(comfy, simular, wf_name, positive, negative, seed, dest, label, idx, dur, fps,
              gw=W, gh=H, frames=None):
    if simular:
        return sim_video(dest, label, idx, dur, fps)
    if frames is None:
        frames = int(round(dur * fps))
    wf = patch_workflow(load_workflow(wf_name), positive, negative, seed, frames=frames,
                        gw=gw, gh=gh)
    pid = comfy.queue(wf)
    return comfy.wait_download(pid, dest)


# ===========================================================================
# Montaje por formato
# ===========================================================================
def _wrap(text, fontsize, factor=0.5):
    """Parte el texto en líneas para que quepa a lo ancho (drawtext no auto-ajusta)."""
    max_chars = max(8, int(W / (fontsize * factor)))
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_chars:
            lines.append(cur); cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return "\n".join(lines)


def _txt(tmpdir, name, text):
    p = os.path.join(tmpdir, f"{name}.txt")
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


def make_textcard(bg_png, beat, cfg, dur, fps, dest, tmpdir):
    """Fondo IA + texto nítido (DM Serif headline + Space Grotesk subhead/kicker) +
    firma de marca 'marli' + pill rojo opcional."""
    brand = cfg.get("brand", {})
    headline_font = _font(brand, "headline", "DMSerifDisplay-Regular.ttf")
    body_font = _font(brand, "body", "SpaceGrotesk-Regular.ttf")
    accent = brand.get("accent_color", "#7a0c0c").lstrip("#")
    sig = brand.get("signature", "marli")

    # Sombra para que el texto se lea sobre cualquier fondo (claro u oscuro).
    SH = "shadowcolor=black@0.6:shadowx=4:shadowy=4"
    draws = []
    if beat.get("kicker"):
        tf = _txt(tmpdir, "kicker", beat["kicker"].upper())
        draws.append(f"drawtext=fontfile='{body_font}':textfile='{tf}':expansion=none:"
                     f"{SH}:fontcolor=white:fontsize=h/34:x=(w-text_w)/2:y=h*0.20")
    if beat.get("headline"):
        fs = H / 14
        tf = _txt(tmpdir, "headline", _wrap(beat["headline"], fs, factor=0.50))
        draws.append(f"drawtext=fontfile='{headline_font}':textfile='{tf}':expansion=none:"
                     f"{SH}:text_align=center:fontcolor=white:fontsize={int(fs)}:line_spacing=14:"
                     f"box=1:boxcolor=black@0.35:boxborderw=28:x=(w-text_w)/2:y=h*0.36")
    if beat.get("subhead"):
        fs = H / 30
        tf = _txt(tmpdir, "subhead", _wrap(beat["subhead"], fs, factor=0.46))
        draws.append(f"drawtext=fontfile='{body_font}':textfile='{tf}':expansion=none:"
                     f"{SH}:text_align=center:fontcolor=white:fontsize={int(fs)}:line_spacing=10:"
                     f"x=(w-text_w)/2:y=h*0.56")
    if beat.get("cta_pill"):
        tf = _txt(tmpdir, "cta", beat.get("cta", "Empieza ya"))
        # Pill: caja redondeada simulada con drawbox + texto encima.
        draws.append(f"drawbox=x=(iw-iw*0.5)/2:y=ih*0.74:w=iw*0.5:h=ih*0.07:"
                     f"color=0x{accent}@1.0:t=fill")
        draws.append(f"drawtext=fontfile='{body_font}':textfile='{tf}':expansion=none:"
                     f"fontcolor=white:fontsize=h/30:x=(w-text_w)/2:y=h*0.755")
    # Firma de marca abajo.
    tf = _txt(tmpdir, "sig", sig)
    draws.append(f"drawtext=fontfile='{headline_font}':textfile='{tf}':expansion=none:"
                 f"{SH}:fontcolor=white@0.95:fontsize=h/26:x=(w-text_w)/2:y=h*0.90")

    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,"
          + ",".join(draws) + f",format=yuv420p")
    run(["ffmpeg", "-y", "-loop", "1", "-i", bg_png, "-t", f"{dur}",
         "-vf", vf, "-r", str(fps),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", dest])
    return dest


def make_slideshow(slide_pngs, beat, cfg, dur, fps, dest, tmpdir):
    """5 imágenes que cambian cada slide_dur; opcional xfade + texto por slide +
    sting de tambor por cambio."""
    brand = cfg.get("brand", {})
    body_font = _font(brand, "body", "SpaceGrotesk-Regular.ttf")
    accent = brand.get("accent_color", "#7a0c0c").lstrip("#")
    slide_dur = float(beat.get("slide_dur", 1.0))
    n = max(1, int(round(dur / slide_dur)))
    # Ajusta el nº de slides para llenar el beat (repite si faltan).
    pngs = [slide_pngs[i % len(slide_pngs)] for i in range(n)]
    texts = beat.get("texts") or []

    parts = []
    for i, png in enumerate(pngs):
        seg = os.path.join(tmpdir, f"slide_{i:02d}.mp4")
        draws = ""
        if i < len(texts) and texts[i]:
            tf = _txt(tmpdir, f"slidetxt_{i}", str(texts[i]))
            draws = (f",drawbox=x=0:y=ih*0.80:w=iw:h=ih*0.12:color=0x{accent}@0.85:t=fill,"
                     f"drawtext=fontfile='{body_font}':textfile='{tf}':expansion=none:"
                     f"fontcolor=white:fontsize=h/22:x=(w-text_w)/2:y=h*0.835")
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1"
              f"{draws},format=yuv420p")
        run(["ffmpeg", "-y", "-loop", "1", "-i", png, "-t", f"{slide_dur}",
             "-vf", vf, "-r", str(fps),
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", seg])
        parts.append(seg)

    listf = os.path.join(tmpdir, "slides.txt")
    with open(listf, "w") as f:
        for p in parts:
            f.write(f"file '{p}'\n")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listf,
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", str(fps), dest])
    return dest


# ===========================================================================
# Audio (TTS opcional + música)
# ===========================================================================
def tts_elevenlabs(text, voice_id, dest):
    """Genera voz con ElevenLabs si hay ELEVENLABS_KEY y red. Devuelve ruta o None."""
    key = os.environ.get("ELEVENLABS_KEY")
    if not key or not text:
        return None
    try:
        body = json.dumps({"text": text,
                           "model_id": "eleven_multilingual_v2"}).encode()
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        req = urllib.request.Request(url, data=body, headers={
            "xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"})
        with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
            f.write(r.read())
        return dest
    except Exception as e:  # noqa: BLE001
        print(f"[aviso] TTS ElevenLabs no disponible ({e}); el beat irá sin voz.")
        return None


def add_voice(clip, voice_audio, music_low, dest, fps):
    """Mete la voz encima del clip (música muy baja la pone el mux final)."""
    run(["ffmpeg", "-y", "-i", clip, "-i", voice_audio,
         "-map", "0:v:0", "-map", "1:a:0", "-shortest",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", dest])
    return dest


# ===========================================================================
# Pipeline de un beat
# ===========================================================================
def process_beat(beat, idx, cfg, comfy, simular, beats_dir, tmproot):
    btype = beat["type"]
    bid = beat.get("id", f"b{idx + 1}")
    n = beat.get("n", idx + 1)
    fps = int(resolve(beat, cfg, "fps", 24))
    dur = float(beat.get("dur", 5))
    style = resolve(beat, cfg, "style", "editorial")
    camera = resolve(beat, cfg, "camera", "static")
    seed = beat_seed(beat, cfg, idx)
    neg = beat.get("negative", NEGATIVE_DEFAULT)
    tmpdir = os.path.join(tmproot, f"beat{n}")
    os.makedirs(tmpdir, exist_ok=True)

    out = os.path.join(beats_dir, f"beat{n}_{btype}_{bid}.mp4")
    # Workflow de imagen (FLUX por defecto; SDXL-Turbo u otro si se indica en el YAML).
    img_wf = cfg.get("image_workflow", "image_flux_dev.json")
    # Backend de vídeo: 'wan' (real) o 'image' (imagen IA + Ken Burns, si no hay Wan).
    video_backend = cfg.get("video_backend", "wan")
    gw, gh = (cfg.get("gen_resolution") or [W, H])[:2]

    if btype in ("cinematic", "ugc"):
        if video_backend == "image":
            prompt = build_prompt(beat.get("prompt", ""), style, camera, is_video=False)
            still = os.path.join(tmpdir, "still.png")
            gen_image(comfy, simular, img_wf, prompt, neg, seed, still, bid, idx, gw, gh)
            clip = make_kenburns(still, os.path.join(tmpdir, "kb.mp4"), dur, fps)
            clip = normalize_clip(clip, os.path.join(tmpdir, "norm.mp4"), dur, fps)
        else:
            prompt = build_prompt(beat.get("prompt", ""), style, camera, is_video=True)
            raw = os.path.join(tmpdir, "raw.mp4")
            vwf = cfg.get("video_workflow", WORKFLOW_BY_TYPE[btype])
            vw, vh = (cfg.get("video_resolution") or [480, 832])[:2]
            wan_fps = int(cfg.get("wan_fps", 16))
            nf = int(round(dur * wan_fps))
            frames = nf - (nf % 4) + 1        # Wan exige longitud 4n+1
            gen_video(comfy, simular, vwf, prompt, neg, seed,
                      raw, bid, idx, dur, fps, vw, vh, frames=frames)
            clip = normalize_clip(raw, os.path.join(tmpdir, "norm.mp4"), dur, fps)
        # UGC: voz opcional (TTS) encima.
        if btype == "ugc":
            audio = beat.get("audio", {}) or {}
            if audio.get("source") == "tts":
                voice = os.path.join(tmpdir, "voice.mp3")
                if not simular and tts_elevenlabs(audio.get("text", ""),
                                                  audio.get("voice_id", ""), voice):
                    clip = add_voice(clip, voice, None,
                                     os.path.join(tmpdir, "voiced.mp4"), fps)
        os.replace(clip, out)

    elif btype == "textcard":
        prompt = build_prompt(beat.get("prompt", "premium abstract background, soft gradients"),
                              style, camera, is_video=False)
        bg = os.path.join(tmpdir, "bg.png")
        gen_image(comfy, simular, img_wf, prompt, neg, seed, bg, bid, idx, gw, gh)
        card = make_textcard(bg, beat, cfg, dur, fps, os.path.join(tmpdir, "card.mp4"), tmpdir)
        normalize_clip(card, out, dur, fps)

    elif btype == "slideshow5":
        slides = beat.get("slides") or [beat.get("prompt", "premium product shot")]
        pngs = []
        for i, sp in enumerate(slides):
            prompt = build_prompt(sp, style, camera, is_video=False)
            dst = os.path.join(tmpdir, f"slide_{i:02d}.png")
            gen_image(comfy, simular, img_wf, prompt, neg,
                      seed + i, dst, bid, idx + i, gw, gh)
            pngs.append(dst)
        show = make_slideshow(pngs, beat, cfg, dur, fps,
                              os.path.join(tmpdir, "show.mp4"), tmpdir)
        normalize_clip(show, out, dur, fps)

    else:
        raise SystemExit(f"Tipo de beat desconocido: {btype}")

    # --- Composite de la mascota Li (desde la foto real, recortada) ---
    li_place = beat.get("li")
    cutout = cfg.get("mascota_cutout")
    if li_place and cutout:
        cpath = cutout if os.path.isabs(cutout) else os.path.join(HERE, cutout)
        if os.path.exists(cpath):
            tmp = os.path.join(tmpdir, "li.mp4")
            overlay_li(out, tmp, cpath, li_place, dur, fps)
            os.replace(tmp, out)

    # --- Voz en off del beat (mp3 pregenerado en vo_dir/vo_<id>.mp3) ---
    vo_dir = cfg.get("vo_dir", "assets/vo")
    vpath = os.path.join(HERE, vo_dir, f"vo_{bid}.mp3")
    if os.path.exists(vpath):
        tmp = os.path.join(tmpdir, "vo.mp4")
        add_vo(out, tmp, vpath, dur)
        os.replace(tmp, out)

    print(f"  beat{n} [{btype}/{bid}] {dur}s -> {os.path.basename(out)}")
    return out


# ===========================================================================
# Ensamblaje final
# ===========================================================================
def assemble(beat_clips, cfg, dest, fps, tmproot):
    listf = os.path.join(tmproot, "beats.txt")
    with open(listf, "w") as f:
        for c in beat_clips:
            f.write(f"file '{c}'\n")
    concat = os.path.join(tmproot, "concat.mp4")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listf,
         "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-r", str(fps),
         "-c:a", "aac", "-b:a", "160k", concat])

    music = cfg.get("music")
    music_path = os.path.join(HERE, music) if music and not os.path.isabs(music) else music
    if music_path and os.path.exists(music_path):
        mix = cfg.get("audio_mix", {})
        music_vol = float(mix.get("music_vol", 0.18))  # música de fondo baja
        # Mezcla: audio del concat (voces UGC) + música a bajo volumen, recortado al vídeo.
        run(["ffmpeg", "-y", "-i", concat, "-stream_loop", "-1", "-i", music_path,
             "-filter_complex",
             f"[1:a]volume={music_vol}[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=0[a]",
             "-map", "0:v:0", "-map", "[a]", "-shortest",
             "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", dest])
    else:
        if music:
            print(f"[aviso] no encuentro la música '{music}'; el anuncio irá con el audio de los beats.")
        os.replace(concat, dest)
    return dest


# ===========================================================================
# Main
# ===========================================================================
def main():
    ap = argparse.ArgumentParser(description="Orquestador de anuncios de Marli (ComfyUI + ffmpeg).")
    ap.add_argument("config", help="Ruta al YAML del anuncio (p.ej. configs/marli_v2.yaml)")
    ap.add_argument("--host", default=os.environ.get("COMFY_HOST", "http://127.0.0.1:8188"),
                    help="URL de ComfyUI (o variable COMFY_HOST)")
    ap.add_argument("--simular", action="store_true",
                    help="No usa GPU: genera placeholders y monta el anuncio igualmente.")
    args = ap.parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    name = cfg.get("name") or os.path.splitext(os.path.basename(args.config))[0]
    fps = int(cfg.get("fps", 24))
    beats = cfg.get("beats", [])
    if not beats:
        raise SystemExit("El config no tiene 'beats'.")

    out_dir = os.path.join(OUT_ROOT, name)
    beats_dir = out_dir
    tmproot = os.path.join(out_dir, "_tmp")
    os.makedirs(beats_dir, exist_ok=True)
    os.makedirs(tmproot, exist_ok=True)

    comfy = None if args.simular else Comfy(args.host)
    print(f"== Marli · anuncio '{name}' · {len(beats)} beats · "
          f"{'SIMULACIÓN' if args.simular else args.host} ==")

    clips = []
    for idx, beat in enumerate(beats):
        clips.append(process_beat(beat, idx, cfg, comfy, args.simular, beats_dir, tmproot))

    final = os.path.join(OUT_ROOT, f"{name}.mp4")
    assemble(clips, cfg, final, fps, tmproot)

    dur = sum(float(b.get("dur", 5)) for b in beats)
    print(f"\n== Listo: {final}  (~{dur:.0f}s) ==")
    print(f"   Beats en: {beats_dir}")


if __name__ == "__main__":
    main()
