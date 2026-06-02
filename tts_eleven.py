#!/usr/bin/env python3
"""
tts_eleven.py — Genera la voz (ElevenLabs) a partir del paquete de producción.

Se ejecuta DENTRO del pod (su egress es abierto; api.elevenlabs.io está bloqueado
en el entorno web). Recorre los segmentos y genera:
  - <segid>.mp3        para el diálogo del avatar (formato ugc -> lip-sync)
  - <segid>_vo.mp3     para la voz en off de cada segmento (mezcla en el montaje)

Requiere ELEVENLABS_API_KEY en el entorno. voz_id se toma de salida.voz_off.voz_id
(o de avatar.voz_id por segmento). Solo usa la librería estándar.

    ELEVENLABS_API_KEY=... python3 tts_eleven.py --package examples/marli_ad01.json --out outputs/voice
"""
import argparse, json, os, sys, time, urllib.request, urllib.error
import pipeline

API = "https://api.elevenlabs.io/v1/text-to-speech/{voice}"
MODEL = "eleven_multilingual_v2"


def tts(text, voice_id, api_key, retries=3, timeout=120):
    body = json.dumps({
        "text": text, "model_id": MODEL,
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "style": 0.0, "use_speaker_boost": True},
    }).encode("utf-8")
    headers = {"xi-api-key": api_key, "Content-Type": "application/json", "Accept": "audio/mpeg"}
    last = None
    for a in range(retries):
        try:
            req = urllib.request.Request(API.format(voice=voice_id), data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read().decode('utf-8','replace')[:300]}"
            if 400 <= e.code < 500 and e.code != 429:
                break
        except Exception as e:  # noqa: BLE001
            last = str(e)
        time.sleep(2 * (a + 1))
    raise RuntimeError(last)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", required=True)
    ap.add_argument("--out", default="outputs/voice")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    pkg = pipeline.load_package(args.package)
    default_voice = (pkg["salida"].get("voz_off") or {}).get("voz_id")
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not args.dry_run and not key:
        sys.exit("Falta ELEVENLABS_API_KEY (ejecuta dentro del pod con tu key).")
    os.makedirs(args.out, exist_ok=True)
    jobs = []
    for s in pipeline.iter_segments(pkg):
        seg = s["seg"]
        av = seg.get("avatar") or {}
        if av.get("dialogo"):
            jobs.append((f"{seg['id']}.mp3", av["dialogo"], av.get("voz_id") or default_voice))
        if seg.get("voz_off"):
            jobs.append((f"{seg['id']}_vo.mp3", seg["voz_off"], default_voice))
    print(f"[i] {len(jobs)} audios a generar (voz por defecto: {default_voice})")
    for name, text, voice in jobs:
        if not voice:
            print(f"  - {name}: SALTADO (sin voz_id)"); continue
        if args.dry_run:
            print(f"  - {name} [{voice}]: {text[:60]}"); continue
        try:
            audio = tts(text, voice, key)
            open(os.path.join(args.out, name), "wb").write(audio)
            print(f"  - {name}: OK {len(audio)//1024} KB")
        except Exception as e:  # noqa: BLE001
            print(f"  - {name}: ERROR {e}")


if __name__ == "__main__":
    main()
