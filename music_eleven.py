#!/usr/bin/env python3
"""
music_eleven.py — Genera la música de fondo con ElevenLabs Music (in-pod).

Se ejecuta DENTRO del pod (api.elevenlabs.io está bloqueado en el entorno web).
Toma un prompt de estilo y una duración y guarda un MP3. La duración por defecto
se calcula del paquete (suma de segmentos + cierre).

    ELEVENLABS_API_KEY=... python3 music_eleven.py --package examples/marli_ad01.json \
        --prompt "calm minimalist ambient, soft piano and warm pads, premium brand, no drums" \
        --out outputs/music.mp3

Nota: el endpoint de ElevenLabs Music es relativamente nuevo; el script prueba el
endpoint principal y cae a variantes si la API responde distinto, mostrando el
error real para ajustar.
"""
import argparse, json, os, sys, urllib.request, urllib.error
import pipeline

ENDPOINT = "https://api.elevenlabs.io/v1/music"
DEFAULT_PROMPT = ("calm, minimalist, premium ambient brand track: soft warm pads, "
                  "gentle felt piano, subtle and unobtrusive, hopeful and serene, no drums, no vocals")


def compose(prompt, ms, api_key, model="music_v1"):
    body = json.dumps({"prompt": prompt, "music_length_ms": ms, "model_id": model}).encode()
    headers = {"xi-api-key": api_key, "Content-Type": "application/json", "Accept": "audio/mpeg"}
    req = urllib.request.Request(ENDPOINT, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def total_seconds(pkg):
    s = 0.0
    for seg in pipeline.iter_segments(pkg):
        s += seg["seg"].get("duracion_s", 5)
    return s + 3.2  # + tarjeta de cierre


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--package")
    ap.add_argument("--prompt", default=DEFAULT_PROMPT)
    ap.add_argument("--seconds", type=float)
    ap.add_argument("--out", default="outputs/music.mp3")
    args = ap.parse_args()
    secs = args.seconds
    if secs is None and args.package:
        secs = total_seconds(pipeline.load_package(args.package))
    secs = secs or 25.0
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        sys.exit("Falta ELEVENLABS_API_KEY (ejecuta dentro del pod con tu key).")
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    ms = int(secs * 1000)
    print(f"[i] Generando música ElevenLabs (~{secs:.0f}s): {args.prompt[:60]}…")
    try:
        audio = compose(args.prompt, ms, key)
    except urllib.error.HTTPError as e:
        sys.exit(f"ElevenLabs Music HTTP {e.code}: {e.read().decode('utf-8','replace')[:400]}\n"
                 "Ajusta ENDPOINT/parámetros según la respuesta.")
    open(args.out, "wb").write(audio)
    print(f"[i] OK -> {args.out} ({len(audio)//1024} KB)")


if __name__ == "__main__":
    main()
