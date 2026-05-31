#!/usr/bin/env bash
# setup_comfy.sh — Setup ÚNICO de ComfyUI en el pod de RunPod para Marli (§3).
# Ejecútalo DENTRO del pod (terminal / Jupyter), no en tu Mac ni en el sandbox.
#
#   bash setup_comfy.sh
#
# Instala los custom nodes y baja los modelos de los 4 formatos. Requiere que el
# pod tenga acceso a HuggingFace (HF_TOKEN si el modelo lo pide).
set -e

COMFY="${COMFY_DIR:-/workspace/ComfyUI}"
cd "$COMFY/custom_nodes"

echo "== Custom nodes =="
[ -d ComfyUI-Manager ] || git clone https://github.com/ltdrdata/ComfyUI-Manager.git
[ -d ComfyUI-WanVideoWrapper ] || git clone https://github.com/kijai/ComfyUI-WanVideoWrapper.git
[ -d ComfyUI-VideoHelperSuite ] || git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git
# Lip-sync para UGC (opcional, cuando la marca lo pida):
# [ -d ComfyUI-LatentSyncWrapper ] || git clone https://github.com/kijai/ComfyUI-LatentSyncWrapper.git

echo "== Modelos =="
cd "$COMFY/models"
mkdir -p unet vae clip diffusion_models

dl() { # dl <carpeta> <archivo> <url>
  if [ ! -f "$1/$2" ]; then
    echo "  bajando $1/$2"
    wget -q --show-progress -O "$1/$2" "$3"
  else
    echo "  ya existe $1/$2"
  fi
}

# FLUX.1 dev (TEXT_CARD + SLIDESHOW_5)
dl unet  flux1-dev.safetensors                    "https://huggingface.co/black-forest-labs/FLUX.1-dev/resolve/main/flux1-dev.safetensors"
dl vae   ae.safetensors                           "https://huggingface.co/black-forest-labs/FLUX.1-dev/resolve/main/ae.safetensors"
dl clip  clip_l.safetensors                       "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors"
dl clip  t5xxl_fp16.safetensors                   "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp16.safetensors"

# Wan 2.2 14B T2V (CINEMATIC + UGC)
dl diffusion_models wan2_2-T2V-A14B_fp8.safetensors        "https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/Wan2_2-T2V-A14B_fp8_e4m3fn.safetensors"
dl clip  umt5_xxl_fp8_e4m3fn_scaled.safetensors   "https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/umt5-xxl-enc-fp8_e4m3fn.safetensors"
dl vae   wan_2.1_vae.safetensors                  "https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/Wan2_1_VAE_bf16.safetensors"

echo ""
echo "== Hecho. Reinicia ComfyUI para que cargue nodos y modelos. =="
echo "   La API quedará en el puerto 8188 (https://<POD_ID>-8188.proxy.runpod.net)."
echo "   NOTA: revisa los nombres EXACTOS de archivo en /object_info y ajusta los"
echo "   workflows si tu repo de modelos usa otros nombres."
