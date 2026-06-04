# SESIÓN 2 — PRODUCTOR (con GPU)

Genera el **banco de assets** (imágenes + clips + voces) del paquete aprobado, en un
solo pod y en lote. NO monta el vídeo final (eso es la S3). Apaga/borra el pod al acabar.

## PROMPT DE ARRANQUE
```
Eres el PRODUCTOR (Sesión 2) del pipeline Marli. Lee CLAUDE.md, REGLAS.md, FORMATOS.md.
Paquete: production_package.json (aprobado en S1). Claves in-pod: OPENAI_API_KEY y/o
ELEVENLABS_API_KEY. Verifica saldo RunPod ANTES de gastar.

Produce el banco de assets en un solo pod: imágenes (OpenAI medium, concurrente),
voz (tts.py, audio-first), clips ComfyUI (comfy_run) y slideshows. DESCARGA cada
asset a local EN CUANTO se genera (R6.2). Escribe outputs/manifest.json (qué es cada
asset, su pieza/segmento, seed/variación). Apaga/BORRA el pod al terminar. NO montes
el vídeo (lo hace la S3).
```

## Requisitos
- `production_package.json` aprobado. `RUNPOD_API_KEY` (env). `OPENAI_API_KEY` y/o
  `ELEVENLABS_API_KEY` (se inyectan in-pod). **Saldo RunPod > 0** (R6.4).

## Flujo (ver comandos en SCALING.md)
1. **Saldo + pod**: verificar `myself.clientBalance`; crear pod H100 SXM (receta en
   CLAUDE.md); esperar `/system_stats`. **No matar el gestor de descargas** (tumba el pod).
2. **Doctor**: `comfy_doctor.py` (modelos OK antes de gastar).
2-bis. **Personajes (una vez, máxima calidad)**: `build_characters.py --package …`
   (gpt-image-1 `high` → `assets/characters/<id>.png`; reutiliza si ya existe). **Sube
   los retratos al input del pod** (`<id>.png`) — son el `start_image` de los UGC.
3. **Imágenes** (in-pod, concurrente): `openai_images.py --package … --out /ComfyUI/input
   --concurrency 6`. Descargar copia a `outputs/images`.
4. **Voz** (in-pod, audio-first): `tts.py --package … --out outputs/voice`. Subir
   `<uid>.mp3` (avatar) al input para el lip-sync.
5. **Clips ComfyUI**: `comfy_run.py --package …` → `outputs/clips` (por `uid`).
   (Si hay `variaciones`, generar N tomas con seeds distintas — R5.1.)
6. **Slideshows** (local): `build_slideshow.py --package …`.
7. **Manifest**: escribir `outputs/manifest.json` (asset → pieza/segmento/uid/seed/tipo).
8. **APAGAR/BORRAR el pod** (R6.1).

## Reglas críticas
- R6.2 descargar al instante (un pod sin saldo se borra a mitad).
- R6.1 un pod por lote; borrar al final.
- No montar aquí: la S2 entrega assets crudos + manifest; la coherencia/edición es S3.
