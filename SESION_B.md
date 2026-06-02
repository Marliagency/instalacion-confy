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
4. **Voz (ElevenLabs, in-pod)**: `tts_eleven.py --package …` → audios; sube los de
   avatar (`<segid>.mp3/.wav`) al `input` del pod para el lip-sync; guarda los `_vo`
   en `outputs/voice` para el montaje.
5. **Clips ComfyUI**: `python3 comfy_run.py --comfy-url <URL> --package …` →
   genera i2v (cinematic/pov/product) y ugc (lipsync) en `outputs/clips`.
6. **Slideshows (local)**: `python3 build_slideshow.py --package … --images outputs/images`.
7. **Montaje final**: `python3 assemble_final.py` (lee orden, textos, VO y música
   del paquete) → `outputs/marli_final.mp4`. Entrega con SendUserFile.
8. **APAGA/BORRA el pod** (stop si lo reusarás; **DELETE** si fue desechable — el
   disco factura aunque esté EXITED).

## Validar `wan_lipsync` (una sola vez)
La plantilla `workflows/api/wan_lipsync.json` está `pendiente_validar`. Con el pod vivo:
1. `curl /object_info` y localiza la cadena de lip-sync (WanVideoWrapper / Wan
   Animate, o un nodo audio-driven; el pod hermano `marli-lipsync` es referencia).
2. Carga el workflow de ejemplo del template
   (`/ComfyUI/user/default/workflows/Wan Animate/…`), pásalo a formato API.
3. Construye el grafo API, añade `LoadImage` (retrato) + nodo de audio
   (`VHS_LoadAudio`/`LoadAudio`) + salida, valida con `/prompt`.
4. Guarda en `workflows/api/wan_lipsync.json` con su mapa `_meta.inject`
   (`image`, `audio`, `positive`, `seed`, `prefix`) y quita `pendiente_validar`.
Tras esto, `comfy_run.py` lo usa igual que `wan_i2v` (reutilizable).

## Gotchas (no repetir errores)
- ComfyUI en `/ComfyUI`, input `/ComfyUI/input`; nunca globs desde `/`.
- 14B i2v usa `wan_2.1_vae` (16ch), no `wan2.2_vae` (48ch).
- Descargar `.mp4` por `/view` requiere header **User-Agent** (si no, 403).
- ffmpeg: `drawbox` usa `iw` (no `w`); `drawtext` con `%` necesita `expansion=none`.
- Jupyter del pod está abierto (sin login): basta la cookie `_xsrf` de `GET /`.
