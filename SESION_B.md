# Sesión B — Productor (CON GPU)

Ejecuta un `production_package.json` validado y entrega el vídeo. Enciende un pod,
genera imágenes (OpenAI) y voz (ElevenLabs) DENTRO del pod, anima con los
workflows ComfyUI **ya guardados**, monta en local y **apaga/borra el pod**.

## Requisitos
- `production_package.json` validado (de la Sesión A).
- `RUNPOD_API_KEY` (env del entorno).
- `OPENAI_API_KEY` y `ELEVENLABS_API_KEY` — NO están en el entorno; se inyectan
  **dentro del pod** (su egress es abierto; ambos hosts están bloqueados en local).
- Local: `apt-get install -y ffmpeg`, `pip install requests websocket-client fonttools jsonschema`.

## Flujo
1. **Arranca pod** H100 SXM (receta en CLAUDE.md: imagen `hearmeman/comfyui-wan-template:v19`,
   `containerDiskInGb 200`, env `download_wan22=true download_wan_animate=true`,
   ports 8188/8888). Espera a `/system_stats`=200.
2. **Doctor**: `python3 comfy_doctor.py --comfy-url <URL>` — verifica que los
   modelos de cada workflow existen (drift). Si faltan, no gastes GPU.
3. **Imágenes (OpenAI, in-pod)**: con `pod_exec.py` ejecuta `openai_images.py
   --package … --quality medium` guardando los PNG en `/ComfyUI/input`; descárgalos
   también a `outputs/images` (vía `/view?type=input`, con header User-Agent).
4. **Voz (in-pod, audio-first)**: `python3 tts.py --package …` → usa ElevenLabs si hay
   key válida, si no cae a OpenAI TTS. Genera `<uid>.mp3` (avatar→lip-sync) y
   `<uid>_vo.mp3` (voz en off). Para los UGC, sube `<uid>.mp3` al input del pod.
   **Música (opcional, ElevenLabs)**: `music_eleven.py --package … --out outputs/music.mp3`
   (si no, usa `assets/bed.wav`).
5. **Clips ComfyUI (todos)**: `python3 comfy_run.py --comfy-url <URL> --package …` →
   i2v (cinematic/pov/product) y ugc (lipsync) en `outputs/clips` (por `uid`).
6. **Slideshows (local)**: `python3 build_slideshow.py --package … --images outputs/images`.
7. **Montaje final**: `python3 assemble_pkg.py --package … --out-dir outputs` →
   **un MP4 por pieza** (`outputs/<pieza_id>.mp4`). Entrega con SendUserFile.

> Para LOTE grande (muchas piezas) ver `SCALING.md`. Descarga imágenes/clips/voces a
> local EN CUANTO se generan (un pod sin saldo RunPod se borra a mitad).
8. **APAGA/BORRA el pod** (stop si lo reusarás; **DELETE** si fue desechable — el
   disco factura aunque esté EXITED).

## Validar `wan_lipsync` — lip-sync por AUDIO (setup de una vez)
Alternativa open-source al Wan 2.7 de Higgsfield: **WAN + InfiniteTalk** (o MultiTalk)
vía ComfyUI-WanVideoWrapper (kijai, ya instalado). OJO: el *Wan Animate* del template
es guiado por VÍDEO, NO por audio — no sirve para esto.

1. **Pod estable** arriba (los H100 SECURE estuvieron tirando pods el 2026-06-03; reintentar).
2. **Bajar pesos una vez** (no vienen con download_wan22): InfiniteTalk/MultiTalk →
   `/ComfyUI/models/diffusion_models`; **wav2vec2** (encoder de audio) → `models/audio_encoders`.
   (La base WAN i2v + vae + umt5 ya están con download_wan22.)
3. `curl /object_info` → localizar nodos de audio de WanVideoWrapper (embeds MultiTalk/
   InfiniteTalk, LoadAudio, wav2vec encode).
4. Construir grafo API: `LoadImage`(retrato) + `LoadAudio`(voz) + wav2vec encode →
   audio embeds → `WanVideoSampler`(i2v+audio) → decode → `VHS_VideoCombine`. Validar con `/prompt`.
5. Guardar en `workflows/api/wan_lipsync.json` con `_meta.inject` =
   `{image, audio, positive, seed, prefix}` y quitar `pendiente_validar`.

Tras esto, `comfy_run.py` lo usa igual que `wan_i2v` (reutilizable). Flujo audio-first:
`openai_tts.py`/`tts_eleven.py` → voz → comfy_run inyecta retrato+voz → clip lip-sync.

## Gotchas (no repetir errores)
- ComfyUI en `/ComfyUI`, input `/ComfyUI/input`; nunca globs desde `/`.
- 14B i2v usa `wan_2.1_vae` (16ch), no `wan2.2_vae` (48ch).
- Descargar `.mp4` por `/view` requiere header **User-Agent** (si no, 403).
- ffmpeg: `drawbox` usa `iw` (no `w`); `drawtext` con `%` necesita `expansion=none`.
- Jupyter del pod está abierto (sin login): basta la cookie `_xsrf` de `GET /`.
