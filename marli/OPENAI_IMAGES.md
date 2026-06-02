# Imágenes UGC con OpenAI (gpt-image-1) — sustituye a Gemini/Qwen

Decisión (2026-06-02): los **stills de referencia** del pipeline se generan con
`gpt-image-1` de OpenAI, NO con Gemini ni con un modelo local de ComfyUI. El pod
solo se enciende para **Wan I2V** (animar el still) y **LatentSync** (lip-sync).

## Activación (acción del USUARIO, una vez)

El sandbox de Claude Code on the web bloquea `api.openai.com`
(`x-deny-reason: host_not_allowed`). Para poder llamarlo:

1. Settings del entorno → **Network access = Custom** → añade `api.openai.com`
   (deja también `*.proxy.runpod.net`, `api.runpod.io`, `rest.runpod.io`).
2. La política de red se fija al arrancar el contenedor → **abre una SESIÓN
   NUEVA** después de guardar.
3. Pega tu API key en `marli/.secrets` (gitignored) en una línea:
   ```
   OPENAI_API_KEY=sk-...
   ```
   La key sale de platform.openai.com con facturación activa. `gpt-image-1`
   suele exigir **verificar la organización** (Settings → Organization → Verify)
   antes de dejarte generar; si da error de verificación, es eso.
4. Comprobar al inicio de la sesión nueva:
   `curl -s -o /dev/null -w "%{http_code}" https://api.openai.com/v1/models`
   → `401` = host permitido y solo falta key correcta (bien); `403` con
   `host_not_allowed` = el allowlist sigue sin aplicarse.

## Uso

```bash
# Texto -> imagen (escena/cara UGC desde cero)
python3 marli/openai_image.py generate \
    --prompt "Selfie UGC de una psicóloga sonriendo en consulta luminosa,
              luz de ventana, estética iPhone, sin texto" \
    --size 1024x1536 --quality high \
    --out marli/assets/scenes/ugc_psico.png

# Referencia + texto -> imagen (mantener a Li o una cara consistente)
python3 marli/openai_image.py edit \
    --ref marli/assets/li_ref.png \
    --prompt "El robot rojo Li sobre el escritorio de una consulta, foto realista, 9:16" \
    --size 1024x1536 --quality high \
    --out marli/assets/scenes/li_escena.png
```

- Tamaños: `1024x1024`, `1024x1536` (vertical, lo más cercano a 9:16),
  `1536x1024`. Para 9:16 exacto, generar `1024x1536` y recortar/encajar en el
  montaje (el orquestador ya lleva todo a 1080x1920).
- Calidad `low` para iterar prompts barato; `high` para el render final.
- Coste orientativo: ~$0.02 (low) a ~$0.19–0.25 (high) por imagen vertical.

## Cómo encaja en el pipeline

1. (pod APAGADO) `openai_image.py` genera los stills → `marli/assets/scenes/`.
2. (pod ON) Wan I2V anima los stills que sean clips → `marli/assets/clips/`.
3. (pod ON) LatentSync hace lip-sync de los clips hablados (ver LIPSYNC_SETUP.md).
4. (pod APAGADO) `comfy_generate.py … --simular` monta el vídeo final.

Solo el paso "generar el still" cambia de motor; el resto es idéntico.
