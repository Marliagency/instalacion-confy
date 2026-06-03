#!/usr/bin/env python3
"""
tts.py — Punto de entrada UNIFICADO de voz (audio-first). Se ejecuta in-pod.

Lee el paquete y, según `salida.voz_off.motor`, genera la voz con ElevenLabs o
con OpenAI TTS. Si el motor es elevenlabs pero falla (plan free / sin permiso /
sin key), cae automáticamente a OpenAI TTS para no bloquear la producción.

Salida (por uid = <pieza>__<segmento>):
  - <uid>.mp3      diálogo del avatar (formato ugc -> entra al lip-sync)
  - <uid>_vo.mp3   voz en off del segmento (se mezcla en el montaje)

Claves (in-pod): ELEVENLABS_API_KEY y/o OPENAI_API_KEY.

    OPENAI_API_KEY=... ELEVENLABS_API_KEY=... python3 tts.py --package pkg.json --out outputs/voice

Voces por defecto: ElevenLabs usa salida.voz_off.voz_id (y avatar.voz_id si está);
OpenAI usa nova (voz en off) y shimmer (avatar).
"""
import argparse, os, sys
import pipeline
import tts_eleven, openai_tts

OA_VO, OA_AVATAR = "nova", "shimmer"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", required=True)
    ap.add_argument("--out", default="outputs/voice")
    ap.add_argument("--force-engine", choices=["elevenlabs", "openai"])
    args = ap.parse_args()
    pkg = pipeline.load_package(args.package)
    motor = args.force_engine or (pkg["salida"].get("voz_off") or {}).get("motor", "openai")
    default_voice = (pkg["salida"].get("voz_off") or {}).get("voz_id")
    el_key = os.environ.get("ELEVENLABS_API_KEY")
    oa_key = os.environ.get("OPENAI_API_KEY")
    os.makedirs(args.out, exist_ok=True)

    # construir trabajos por uid (avatar + voz en off)
    jobs = []  # (filename, text, el_voice, oa_voice)
    for s in pipeline.iter_segments(pkg):
        seg = s["seg"]; uid = s["uid"]
        av = seg.get("avatar") or {}
        if av.get("dialogo"):
            jobs.append((f"{uid}.mp3", av["dialogo"], av.get("voz_id") or default_voice, OA_AVATAR))
        if seg.get("voz_off"):
            jobs.append((f"{uid}_vo.mp3", seg["voz_off"], default_voice, OA_VO))

    use_eleven = motor == "elevenlabs" and bool(el_key)
    print(f"[i] {len(jobs)} audios | motor preferido: {motor} | ElevenLabs activo: {use_eleven}", flush=True)
    ok = 0
    for name, text, el_voice, oa_voice in jobs:
        audio = None
        if use_eleven and el_voice:
            try:
                audio = tts_eleven.tts(text, el_voice, el_key)
            except Exception as e:  # noqa: BLE001
                print(f"    {name}: ElevenLabs falló ({str(e)[:80]}) → fallback OpenAI", flush=True)
        if audio is None:
            if not oa_key:
                print(f"    {name}: SALTADO (sin OPENAI_API_KEY para fallback)"); continue
            audio = openai_tts.tts(text, oa_voice, oa_key)
        open(os.path.join(args.out, name), "wb").write(audio)
        print(f"  - {name}: OK {len(audio)//1024} KB", flush=True); ok += 1
    print(f"[i] voz lista: {ok}/{len(jobs)}")


if __name__ == "__main__":
    main()
