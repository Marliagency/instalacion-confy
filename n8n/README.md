# n8n — un webhook = un vídeo (contrato)

> n8n **solo dispara** `studio.py make`. No reimplementa la lógica del estudio:
> ni el manifiesto, ni el gate, ni el montaje, ni el ciclo del pod. Encola, agenda
> y reporta estado. La inteligencia vive en `studio.py` + `engine/llm.py`.

## Contrato del webhook

**Entrada** (POST JSON al webhook de n8n):
```json
{ "slug": "marli", "brief": "anuncio UGC de 30s sobre X con gancho Y",
  "max_cost": 3, "approve": false, "blueprint": null, "name": null }
```

**Qué hace n8n con eso:** lo pasa tal cual al entrypoint del pod:
```
python3 studio_webhook.py '{"slug":"...","brief":"...","max_cost":N}'
```
que ejecuta `studio.py make <slug> --brief "<brief>" --max-cost N`.

**Salida** (stdout JSON del entrypoint, que n8n reenvía):
```json
{ "ok": true, "exit": 0, "slug": "marli", "outputs_dir": "projects/marli/outputs", "log": "..." }
```

## Comportamiento (paradas)

- **Lote barato y con assets completos** → `make` produce el vídeo de principio a
  fin sin intervención. `ok: true`.
- **Coste estimado > `max_cost`** → `make` **para** (PARADA 2) y devuelve el plan
  con el coste. `ok: false`. n8n notifica y espera; al reenviar con `"approve": true`
  se fuerza la producción.
- **Faltan assets de usuario o estructura incompleta** → `make` **para** (PARADA 1)
  y lista exactamente qué archivos faltan y en qué ruta. `ok: false`. No se gasta GPU.

## Flujo n8n sugerido (nodos)

1. **Webhook** (trigger) → recibe `{slug, brief, max_cost}`.
2. **Execute Command / SSH** → llama al entrypoint en el pod (o un runner con el repo
   y `RUNPOD_API_KEY` + `ANTHROPIC_API_KEY` + claves de motores en el entorno).
3. **IF `ok == false` y log contiene "PARADA 2"** → notificar (Slack/email) con el
   coste y un botón que reenvía el mismo webhook con `approve: true`.
4. **IF `ok == false` y "PARADA 1"** → notificar la lista de assets a aportar.
5. **IF `ok == true`** → publicar/avisar con `outputs_dir`.

## Requisitos del runner/pod

- Repo clonado + `pip install -r` (anthropic, jsonschema, requests, websocket-client).
- Env: `ANTHROPIC_API_KEY` (creatividad), `RUNPOD_API_KEY` (pod GPU),
  claves de ElevenLabs/OpenAI (voz/imagen in-pod). `make` enciende el pod solo
  durante el lote y lo apaga al terminar (fases A→J).

> Nota: la fase GPU end-to-end de `produce` (render de clips frescos) se completa en
> una iteración aparte; hoy `make` ejecuta brief→pieza→fill→gate→montaje y reutiliza
> clips presentes. El contrato del webhook no cambia cuando se complete esa fase.
