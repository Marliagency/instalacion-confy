#!/bin/bash
# SessionStart: deja la sesión lista (ffmpeg + deps Python) sin pasos manuales.
command -v ffmpeg >/dev/null 2>&1 || { apt-get update -qq >/dev/null 2>&1; apt-get install -y -qq ffmpeg >/dev/null 2>&1; }
pip install -q requests websocket-client jsonschema fonttools >/dev/null 2>&1 || true
echo "entorno listo: ffmpeg $(command -v ffmpeg >/dev/null && echo OK || echo FALTA)"
