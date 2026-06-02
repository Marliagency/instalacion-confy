# Lip-sync (LatentSync 1.6) — provisión del pod y causa raíz del artefacto

LatentSync corre en el pod `sw0wxuoc6kzx2r` vía el nodo
`ComfyUI-LatentSyncWrapper` (ComfyUI en `/ComfyUI`).

## ⚠️ Causa raíz del "confeti arcoíris" sobre la boca (RESUELTO)

El artefacto de ruido de colores sobre la boca **no** era resolución ni el
modelo UNet. Era el **VAE**: el nodo busca el VAE en
`/ComfyUI/custom_nodes/ComfyUI-LatentSyncWrapper/checkpoints/vae/sd-vae-ft-mse.safetensors`
y, si no lo encuentra, **instancia un AutoencoderKL con pesos aleatorios**
(`scripts/inference.py` → "Local VAE not found ... creating VAE with standard
configuration"). Un VAE sin entrenar decodifica los latentes de la boca como
ruido → confeti de colores.

## El entorno del pod es EFÍMERO

Al hacer `stop`/`start` del pod se pierden los `pip install` y, según el caso,
los checkpoints fuera del network volume. Antes de generar lip-sync hay que
reprovisionar SIEMPRE (idempotente; si ya está, no descarga nada):

```bash
python3 marli/provision_lipsync.py    # usa /tmp/podsh.py para hablar con el pod
```

Esto, en el pod:
1. `pip install torchcodec insightface`  (el nodo los exige; sin torchcodec
   falla con "TorchCodec is required for save_with_torchcodec").
2. Descarga `ByteDance/LatentSync-1.6` → `latentsync_unet.pt` (4.8 GB) +
   `whisper/tiny.pt` (73 MB) a `checkpoints/`.
3. Descarga `stabilityai/sd-vae-ft-mse-original` →
   `vae-ft-mse-840000-ema-pruned.safetensors` (335 MB) y lo copia a
   `checkpoints/vae/sd-vae-ft-mse.safetensors`  ← **la pieza que faltaba**.

Tras provisionar, **reinicia ComfyUI** (`POST /api/manager/reboot`) para que
recargue los pesos, y al re-encolar cambia el `seed` si ComfyUI te sirve un
resultado cacheado (0 s = caché).

## Generar

```bash
python3 /tmp/lipsync2.py   # VHS_LoadVideo(force_rate 25) + VHS_LoadAudioUpload
                           # + LatentSyncNode(seed, lips_expression 1.5, steps 20)
                           # + VHS_VideoCombine(25fps, audio=voz)
```
Sube primero los inputs (`/upload/image` sirve para vídeo y audio) porque
`/ComfyUI/input` también se vacía al reiniciar el pod.

Salidas → `marli/assets/clips/beat1_lipsync.mp4`, `beat6_lipsync.mp4`.
