# Lip-sync real (UGC) — InfiniteTalk en ComfyUI · RECETA VALIDADA (2026-06-04)

Avatar consistente + voz → labios sincronizados de verdad. Motor: **WAN 2.1 i2v +
InfiniteTalk** (kijai WanVideoWrapper). Workflow validado: `workflows/api/wan_lipsync.json`.
Coste real de la sesión: **~$0.86** (H100, modelos + 2 clips).

## Modelos a descargar UNA vez (no vienen con el template)
En el pod (boot con todos los `download_*=false` → rápido; bájalos a mano):
```bash
KJ=https://huggingface.co/Kijai/WanVideo_comfy/resolve/main
CO=https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files
wget -cP /ComfyUI/models/diffusion_models $KJ/Wan2_1-I2V-14B-480P_fp8_e4m3fn.safetensors
wget -cP /ComfyUI/models/diffusion_models $KJ/InfiniteTalk/Wan2_1-InfiniTetalk-Single_fp16.safetensors
wget -cP /ComfyUI/models/vae            $KJ/Wan2_1_VAE_bf16.safetensors
wget -cP /ComfyUI/models/text_encoders  $KJ/umt5-xxl-enc-bf16.safetensors
wget -cP /ComfyUI/models/clip_vision     $CO/clip_vision/clip_vision_h.safetensors
wget -O  /ComfyUI/models/loras/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors \
        $KJ/Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors
# wav2vec se auto-descarga (nodo DownloadAndLoadWav2VecModel: TencentGameMate/chinese-wav2vec2-base)
```
~35 GB en total. `comfy_doctor.py` verifica que existen.

## Cómo se generó (reproducible)
1. **Personaje** (una vez): `build_characters.py` → `assets/characters/li_psicologa.png`
   (gpt-image-1 **high**). Súbelo a `/ComfyUI/input/`.
2. **Voz** (audio-first): `tts.py` con **ElevenLabs** (cuenta de PAGO; voz ES
   "Sara Martin" `KHCvMklQZZo0O30ERnVn`, modelo `eleven_multilingual_v2`). Sube el
   `.mp3` a `/ComfyUI/input/`.
3. **Workflow**: `workflows/api/wan_lipsync.json` (ya en formato API). Inyecta
   `image`=retrato, `audio`=voz, `positive`=prompt de escena, `prefix`. Encola en `/prompt`.
4. Descarga el `.mp4` por `/view` (header User-Agent). Vertical: `WanVideoImageToVideoMultiTalk`
   y `ImageResizeKJv2` a `width=480 height=832`.

## Gotchas resueltos
- El ejemplo kijai usa GGUF; aquí usamos **fp8/fp16 safetensors** (H100 sobra de VRAM):
  `WanVideoModelLoader` con `quantization=fp8_e4m3fn`.
- **MelBandRoFormer** (separación de voz) NO está instalado → se **bypassea**
  (`MultiTalkWav2VecEmbeds.audio_1` ← `LoadAudio` directo). Para voz TTS limpia no hace falta.
- Conversión UI→API del ejemplo de 47 nodos con **`ui2api.py`** (resuelve Set/Get) +
  poda por alcanzabilidad desde la salida (quedan 18 nodos).
- ElevenLabs: el plan **gratuito** da 402 en la API aunque tengas créditos; hace falta
  plan de **pago** (Starter+).

## Reutilización (a escala)
`comfy_run.py` usa `wan_lipsync.json` para los segmentos `ugc` (inyecta retrato del
personaje + voz). Mismo personaje en todos los UGC (R8) → cero regeneración de cara.
