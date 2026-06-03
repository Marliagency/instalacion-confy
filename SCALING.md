# Producir a volumen — "100 vídeos en 2 sesiones"

El sistema ya es **multi-pieza**: un único `production_package.json` con N piezas
→ **N vídeos** (uno por pieza). `assemble_pkg.py` saca un MP4 por pieza
(`outputs/<pieza_id>.mp4`). Los nombres internos usan `uid = <pieza>__<segmento>`,
así N piezas no colisionan.

## Las 2 sesiones
- **Sesión A — Guionista (sin GPU, $0):** escribe UN paquete con todas las piezas
  (5, 20, 100…). Valida con `python3 pipeline.py paquete.json`. Commit. Ver `SESION_A.md`.
- **Sesión B — Productor (1 pod, todo en lote):** ver `SESION_B.md`. Clave: **un solo
  pod** procesa TODO (amortiza el arranque/descarga, ~5-10 min una vez).

## Capacidad y coste (H100, medidos)
- **WAN i2v 14B, 4 pasos lightx2v:** ~20-30 s por clip de 5 s → **~100-120 clips por hora de pod**.
- **Imágenes gpt-image-1 `medium` con `--concurrency 6`:** ~1.000/hora, ~$0.04 c/u.
- **Voz (OpenAI/ElevenLabs):** segundos por línea, céntimos.
- **Slideshow + montaje:** local, sin GPU.

| Objetivo | Clips WAN | GPU (pod-horas) | Coste aprox. |
|---|---|---|---|
| 100 vídeos de 5 s (1 clip c/u) | ~100 | ~1 h | ~$3.3 GPU + ~$4 img ≈ **$8** |
| 100 anuncios multi-formato (~4 clips + slideshow) | ~400 | ~3.5-4 h | ~$13 GPU + ~$36 img ≈ **$50** |

El cuello de botella es el tiempo de GPU por clip. Todo lo demás (imágenes, voz,
montaje) es barato y rápido. **100 clips de 5 s caben en una sola Sesión B (~1 pod-hora).**

## Comandos de la Sesión B (en lote)
```bash
# 0. Pod arriba + doctor
python3 comfy_doctor.py --comfy-url $URL
# 1. TODAS las imágenes (in-pod, concurrente) -> /ComfyUI/input
OPENAI_API_KEY=... python3 openai_images.py --package paquete.json --out /ComfyUI/input --concurrency 6
# 2. TODA la voz (in-pod; ElevenLabs si hay key, si no OpenAI) -> outputs/voice
OPENAI_API_KEY=... ELEVENLABS_API_KEY=... python3 tts.py --package paquete.json --out outputs/voice
# 3. TODOS los clips ComfyUI (i2v / lipsync) -> outputs/clips
python3 comfy_run.py --comfy-url $URL --package paquete.json --out outputs/clips
# 4. Slideshows (local) -> outputs/clips
python3 build_slideshow.py --package paquete.json --images outputs/images
# 5. Montaje: un MP4 por pieza -> outputs/
python3 assemble_pkg.py --package paquete.json --out-dir outputs
# 6. APAGAR/BORRAR el pod
```

## Requisitos para arrancar (lo que falta hoy)
1. **Saldo RunPod** > $0 — **ahora hay $0.19** (por eso los pods morían a los ~3 min).
   Para 1 pod-hora H100 (~$3.5) recarga con margen (p.ej. $15-20).
2. **OPENAI_API_KEY** — disponible (se inyecta in-pod).
3. **ElevenLabs (opcional, mejor voz/música):** plan de pago + key con permisos
   `text_to_speech`, `voices_read` (+ `music_generation` si quieres su música) + `voice_id`.
   Si no, `tts.py` cae a OpenAI TTS automáticamente.

## Notas de coste/robustez
- Un solo pod por lote (no recrear por vídeo).
- `comfy_doctor.py` verifica modelos antes de gastar GPU.
- Imagen `medium` + 4 pasos lightx2v = mínimo coste con buena calidad.
- Descargar voces/clips a local **en cuanto se generan** (un pod sin saldo se borra).
