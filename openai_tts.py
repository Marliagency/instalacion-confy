#!/usr/bin/env python3
"""
openai_tts.py — Voz con OpenAI TTS (in-pod), fallback cuando ElevenLabs no está
disponible. Misma salida que tts_eleven.py:
  - <segid>.mp3      diálogo del avatar (ugc)
  - <segid>_vo.mp3   voz en off del segmento

Voces OpenAI (multilingües, sirven para español): narrador = 'nova',
avatar = 'shimmer' (configurable). Requiere OPENAI_API_KEY. Solo stdlib.

    OPENAI_API_KEY=... python3 openai_tts.py --package examples/marli_ad01.json --out outputs/voice
"""
import argparse, json, os, sys, time, urllib.request, urllib.error
import pipeline

URL = "https://api.openai.com/v1/audio/speech"


def tts(text, voice, api_key, model="gpt-4o-mini-tts", retries=3):
    body = json.dumps({"model": model, "voice": voice, "input": text, "response_format": "mp3"}).encode()
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    last = None
    for a in range(retries):
        try:
            req = urllib.request.Request(URL, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read().decode('utf-8','replace')[:200]}"
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
    ap.add_argument("--voice-vo", default="nova")
    ap.add_argument("--voice-avatar", default="shimmer")
    args = ap.parse_args()
    pkg = pipeline.load_package(args.package)
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        sys.exit("Falta OPENAI_API_KEY (in-pod).")
    os.makedirs(args.out, exist_ok=True)
    jobs = []
    for s in pipeline.iter_segments(pkg):
        seg = s["seg"]
        av = seg.get("avatar") or {}
        if av.get("dialogo"):
            jobs.append((f"{seg['id']}.mp3", av["dialogo"], args.voice_avatar))
        if seg.get("voz_off"):
            jobs.append((f"{seg['id']}_vo.mp3", seg["voz_off"], args.voice_vo))
    print(f"[i] {len(jobs)} audios (OpenAI TTS)", flush=True)
    for name, text, voice in jobs:
        try:
            audio = tts(text, voice, key)
            open(os.path.join(args.out, name), "wb").write(audio)
            print(f"  - {name} [{voice}]: OK {len(audio)//1024} KB", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"  - {name}: ERROR {e}", flush=True)


if __name__ == "__main__":
    main()
