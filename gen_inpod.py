#!/usr/bin/env python3
"""
gen_inpod.py — Genera in-pod los assets que requieren red abierta (OpenAI /
ElevenLabs / HuggingFace) para el paquete demo_v2 y los descarga a local.

Pasos (todo DENTRO del pod vía Jupyter; las claves se inyectan en el código que
se ejecuta allí, nunca se commitean):
  1. Retrato de la creadora (gpt-image-1 high) -> assets/characters/li_creadora.png
     y copia a /ComfyUI/input/li_creadora.png (start_image del lip-sync).
  2. Voces del avatar (ElevenLabs) de los segmentos ugc -> outputs/voice/<uid>.mp3
     y copia a /ComfyUI/input/<uid>.mp3.
  3. Música de acción (ElevenLabs Music) -> outputs/music_action.mp3.
  4. Modelos InfiniteTalk (fetch lipsync) en /ComfyUI/models.

Descarga vía base64 por stdout (determinista, sin depender de la raíz de Jupyter).

    OPENAI_API_KEY=... ELEVENLABS_API_KEY=... python3 gen_inpod.py POD_ID \
        --package examples/marli_demo_v2.json
"""
import argparse, base64, json, os, sys
import pipeline
from pod_exec import PodJupyter

INPUT_DIR = "/ComfyUI/input"
MODELS_DIR = "/ComfyUI/models"

# Stack InfiniteTalk (igual que fetch_models.LIPSYNC_MODELS)
KJ = "https://huggingface.co/Kijai/WanVideo_comfy/resolve/main"
CO21 = "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files"
LIPSYNC_MODELS = [
    ("diffusion_models", f"{KJ}/Wan2_1-I2V-14B-480P_fp8_e4m3fn.safetensors"),
    ("diffusion_models", f"{KJ}/InfiniteTalk/Wan2_1-InfiniTetalk-Single_fp16.safetensors"),
    ("vae",              f"{KJ}/Wan2_1_VAE_bf16.safetensors"),
    ("text_encoders",    f"{KJ}/umt5-xxl-enc-bf16.safetensors"),
    ("clip_vision",      f"{CO21}/clip_vision/clip_vision_h.safetensors"),
    ("loras",            f"{KJ}/Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors"),
]


def fetch_b64(pj, pod_path, local_path):
    """Lee un fichero del pod en base64 (troceado) y lo guarda en local."""
    # Trocea con sleep para no superar el iopub data-rate-limit de Jupyter (~1MB/s)
    code = (
        "import base64,time\n"
        f"d=open({pod_path!r},'rb').read()\n"
        "b=base64.b64encode(d).decode()\n"
        "print('LEN',len(d),flush=True)\n"
        "for i in range(0,len(b),90000):\n"
        "    print('B64',b[i:i+90000],flush=True); time.sleep(0.25)\n"
        "print('END',flush=True)\n"
    )
    out = pj.run(code, timeout=300)
    chunks = [l[4:] for l in out.splitlines() if l.startswith("B64 ")]
    data = base64.b64decode("".join(chunks))
    os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
    open(local_path, "wb").write(data)
    return len(data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pod_id")
    ap.add_argument("--package", required=True)
    ap.add_argument("--skip-models", action="store_true")
    ap.add_argument("--skip-avatar", action="store_true", help="reutiliza el retrato ya generado")
    args = ap.parse_args()

    okey = os.environ.get("OPENAI_API_KEY")
    ekey = os.environ.get("ELEVENLABS_API_KEY")
    if not (okey and ekey):
        sys.exit("Faltan OPENAI_API_KEY / ELEVENLABS_API_KEY en el entorno local.")

    pkg = pipeline.load_package(args.package)
    size = pipeline.image_size(pkg)
    char = list(pipeline.iter_characters(pkg))[0]          # li_creadora
    voz_id = pkg["salida"]["voz_off"]["voz_id"]
    ugc = [s for s in pipeline.iter_segments(pkg) if s["formato"] == "ugc"]

    pj = PodJupyter(args.pod_id, password="open")  # Jupyter del template está abierto
    print(f"[i] conectado a Jupyter del pod {args.pod_id}", flush=True)
    try:
        # ---- 0. preparar dirs ----
        pj.run(f"import os; os.makedirs({INPUT_DIR!r},exist_ok=True); print('input ok')")

        # ---- 1. retrato creadora (gpt-image-1 high) ----
        if args.skip_avatar and os.path.isfile(char["retrato"]):
            print(f"[1] retrato {char['id']}: REUTILIZADO ({char['retrato']})")
            inp = INPUT_DIR + "/li_creadora.png"
            present = "True" in pj.run(f"import os; print(os.path.isfile({inp!r}))")
            if not present:   # pod nuevo: subir el retrato local exacto (persistencia)
                b64 = base64.b64encode(open(char["retrato"], "rb").read()).decode()
                pj.run(f"import base64; open({inp!r},'wb').write(base64.b64decode({b64!r})); print('UP_OK')")
                print(f"    subido a {inp}")
        else:
            print(f"[1] retrato {char['id']} (gpt-image-1 high, {size})…", flush=True)
            code = (
                "import os,base64,json,urllib.request\n"
                f"os.environ['K']={okey!r}\n"
                f"prompt={char['prompt']!r}\n"
                "body=json.dumps({'model':'gpt-image-1','prompt':prompt,'size':"
                f"{size.split('x')[0]+'x'+size.split('x')[1]!r}"
                ",'quality':'high','n':1}).encode()\n"
                "req=urllib.request.Request('https://api.openai.com/v1/images/generations',data=body,"
                "headers={'Authorization':'Bearer '+os.environ['K'],'Content-Type':'application/json'})\n"
                "for attempt in range(6):\n"
                "    try:\n"
                "        r=urllib.request.urlopen(req,timeout=300); j=json.load(r); break\n"
                "    except Exception as e:\n"
                "        print('retry',attempt,str(e)[:120]); import time; time.sleep(8)\n"
                "else:\n"
                "    raise SystemExit('openai failed')\n"
                "png=base64.b64decode(j['data'][0]['b64_json'])\n"
                f"open({INPUT_DIR+'/li_creadora.png'!r},'wb').write(png)\n"
                "print('OK_IMG',len(png))\n"
            )
            out = pj.run(code, timeout=400)
            print("   ", [l for l in out.splitlines() if l.startswith("OK_IMG") or l.startswith("retry")])
            n = fetch_b64(pj, INPUT_DIR + "/li_creadora.png", char["retrato"])
            print(f"    -> {char['retrato']} ({n//1024} KB)")

        # ---- 2. voces (ElevenLabs) — diálogo de avatar (ugc) + voz en off ----
        # Ajustes algo más expresivos/enérgicos para el tono de cierre tipo Belfort.
        def gen_voice(text, pod_path, local_path):
            code = (
                "import os,json,urllib.request\n"
                f"key={ekey!r}\n"
                f"text={text!r}\n"
                f"voice={voz_id!r}\n"
                "body=json.dumps({'text':text,'model_id':'eleven_multilingual_v2',"
                "'voice_settings':{'stability':0.4,'similarity_boost':0.85,'style':0.45,'use_speaker_boost':True}}).encode()\n"
                "req=urllib.request.Request('https://api.elevenlabs.io/v1/text-to-speech/'+voice,"
                "data=body,headers={'xi-api-key':key,'Content-Type':'application/json','Accept':'audio/mpeg'})\n"
                "try:\n"
                f"    a=urllib.request.urlopen(req,timeout=180).read(); open({pod_path!r},'wb').write(a); print('OK_VOICE',len(a))\n"
                "except urllib.error.HTTPError as e:\n"
                "    print('VOICE_HTTP',e.code,e.read().decode('utf-8','replace')[:300])\n"
            )
            out = pj.run(code, timeout=240)
            tag = [l for l in out.splitlines() if l.startswith(("OK_VOICE", "VOICE_HTTP"))]
            print("   ", tag)
            if any(l.startswith("OK_VOICE") for l in tag):
                n = fetch_b64(pj, pod_path, local_path)
                print(f"    -> {local_path} ({n//1024} KB)")
                return True
            return False

        for s in ugc:                              # diálogo del avatar -> input (lip-sync)
            uid = s["uid"]; dialog = (s["seg"].get("avatar") or {}).get("dialogo", "")
            print(f"[2] voz avatar {uid} (Cristina)…", flush=True)
            if not gen_voice(dialog, f"{INPUT_DIR}/{uid}.mp3", f"outputs/voice/{uid}.mp3"):
                print("    !! voz falló — revisar voice_id (¿Cristina añadida a la cuenta?)")
        for s in pipeline.iter_segments(pkg):      # voz en off de segmentos narrados
            vo = s["seg"].get("voz_off")
            if not vo or s["formato"] == "ugc":
                continue
            uid = s["uid"]
            print(f"[2b] voz en off {uid} (Cristina)…", flush=True)
            gen_voice(vo, f"{INPUT_DIR}/{uid}_vo.mp3", f"outputs/voice/{uid}_vo.mp3")

        # ---- 3. música de acción (ElevenLabs Music) ----
        secs = sum(s["seg"].get("duracion_s", 5) for s in pipeline.iter_segments(pkg)) + 3.2
        ms = int(secs * 1000)
        prompt_mus = ("energetic modern upbeat advertising track, driving rhythmic percussion, "
                      "punchy claps and snappy hi-hats, bright plucky synth, warm bass, motivational "
                      "and dynamic, building momentum, clean premium commercial bed, no vocals")
        print(f"[3] música de acción (~{secs:.0f}s)…", flush=True)
        code = (
            "import os,json,urllib.request\n"
            f"key={ekey!r}\n"
            f"body=json.dumps({{'prompt':{prompt_mus!r},'music_length_ms':{ms},'model_id':'music_v1'}}).encode()\n"
            "req=urllib.request.Request('https://api.elevenlabs.io/v1/music',data=body,"
            "headers={'xi-api-key':key,'Content-Type':'application/json','Accept':'audio/mpeg'})\n"
            "try:\n"
            "    a=urllib.request.urlopen(req,timeout=300).read()\n"
            f"    open({INPUT_DIR+'/music_action.mp3'!r},'wb').write(a)\n"
            "    print('OK_MUSIC',len(a))\n"
            "except urllib.error.HTTPError as e:\n"
            "    print('MUSIC_HTTP',e.code,e.read().decode('utf-8','replace')[:300])\n"
        )
        out = pj.run(code, timeout=360)
        print("   ", [l for l in out.splitlines() if l.startswith("OK_MUSIC") or l.startswith("MUSIC_HTTP")])
        if "OK_MUSIC" in out:
            n = fetch_b64(pj, f"{INPUT_DIR}/music_action.mp3", "outputs/music_action.mp3")
            print(f"    -> outputs/music_action.mp3 ({n//1024} KB)")
        else:
            print("    !! música falló; revisar endpoint (se usará assets/bed.wav de fallback)")

        # ---- 4. modelos InfiniteTalk ----
        if not args.skip_models:
            print("[4] descargando stack InfiniteTalk (in-pod)…", flush=True)
            jobs = json.dumps(LIPSYNC_MODELS)
            code = (
                "import os,subprocess,json\n"
                f"M={MODELS_DIR!r}; jobs=json.loads({jobs!r})\n"
                "procs=[]\n"
                "for sub,url in jobs:\n"
                "    d=os.path.join(M,sub); os.makedirs(d,exist_ok=True)\n"
                "    fn=url.split('/')[-1]; p=os.path.join(d,fn)\n"
                "    if os.path.isfile(p) and os.path.getsize(p)>1e6:\n"
                "        print('REUSE',sub,fn); continue\n"
                "    print('GET',sub,fn,flush=True)\n"
                "    procs.append(subprocess.Popen(['wget','-q','-c','-P',d,url]))\n"
                "rc=[p.wait() for p in procs]\n"
                "print('DL_DONE',all(r==0 for r in rc))\n"
            )
            out = pj.run(code, timeout=1800)
            print("   ", [l for l in out.splitlines() if l.startswith(("GET","REUSE","DL_DONE"))])
    finally:
        pj.close()
    print("[i] gen_inpod completado.")


if __name__ == "__main__":
    main()
