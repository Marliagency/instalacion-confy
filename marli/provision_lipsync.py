#!/usr/bin/env python3
"""Reprovisiona el pod para lip-sync (LatentSync 1.6). Idempotente.

El entorno del pod es efímero: al stop/start se pierden los pip install y los
checkpoints. Este script deja todo listo. Causa raíz del confeti de colores
sobre la boca: faltaba el VAE sd-vae-ft-mse → AutoencoderKL con pesos
aleatorios → ruido. Aquí se descargan UNet + whisper + VAE y se instala
torchcodec + insightface. Ver LIPSYNC_SETUP.md.

Uso:
    python3 marli/provision_lipsync.py
Requiere /tmp/podsh.py (cliente de terminal Jupyter del pod).
"""
import sys, time
sys.path.insert(0, "/tmp")
import podsh  # noqa: E402

NODE = "/ComfyUI/custom_nodes/ComfyUI-LatentSyncWrapper"
CKPT = f"{NODE}/checkpoints"

PROVISION = r'''
set -e
pip install -q torchcodec insightface 2>&1 | tail -2 || true
python - <<'PY'
import os, shutil
os.environ['HF_HUB_ENABLE_HF_TRANSFER']='1'
from huggingface_hub import snapshot_download, hf_hub_download
ckpt = "%s"
# UNet + whisper
need_unet = not os.path.exists(os.path.join(ckpt,"latentsync_unet.pt"))
need_whis = not os.path.exists(os.path.join(ckpt,"whisper","tiny.pt"))
if need_unet or need_whis:
    snapshot_download(repo_id="ByteDance/LatentSync-1.6",
        allow_patterns=["latentsync_unet.pt","whisper/tiny.pt"],
        local_dir=ckpt, local_dir_use_symlinks=False)
# VAE (la pieza que faltaba)
vae_dst = os.path.join(ckpt,"vae","sd-vae-ft-mse.safetensors")
if not os.path.exists(vae_dst):
    os.makedirs(os.path.dirname(vae_dst), exist_ok=True)
    f = hf_hub_download(repo_id="stabilityai/sd-vae-ft-mse-original",
                        filename="vae-ft-mse-840000-ema-pruned.safetensors")
    shutil.copy2(f, vae_dst)
print("UNET", os.path.getsize(os.path.join(ckpt,"latentsync_unet.pt")))
print("WHISPER", os.path.getsize(os.path.join(ckpt,"whisper","tiny.pt")))
print("VAE", os.path.getsize(vae_dst))
print("PROVISION_OK")
PY
''' % CKPT


def main():
    print("[provision] instalando deps + descargando checkpoints en el pod...")
    out = podsh.run(PROVISION, total=900)
    print(out)
    if "PROVISION_OK" not in out:
        print("[provision] ⚠️ no se confirmó OK; revisa la salida.")
        sys.exit(1)
    print("[provision] OK. Reinicia ComfyUI (/api/manager/reboot) antes de generar.")


if __name__ == "__main__":
    main()
