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

## n8n Cloud (sin Execute Command) → `studio_server.py` por HTTP

En **n8n Cloud** (`marliagency.app.n8n.cloud`) **no existe** el nodo *Execute Command*:
n8n no puede ejecutar `studio.py` directamente. Solución fiel al contrato: n8n hace un
**HTTP POST** a un endpoint que ejecuta `studio.py make`. Ese endpoint es `studio_server.py`
(stdlib, sin dependencias nuevas).

**Workflow ya creado en la cuenta:** *"Estudio — make video (HTTP → studio.py)"*
(`Webhook POST make-video` → `Normalizar petición` → `Disparar studio.py make` (HTTP) →
`IF ok` → responde 200 vídeo / 422 PARADA). Queda **inactivo** hasta configurar 2 cosas:

1. **Levantar el endpoint** en un host con el repo + claves (no necesita GPU propia;
   `studio.py make` enciende/apaga el pod por la API de RunPod durante el lote):
   ```
   STUDIO_TOKEN=<secreto> python3 studio_server.py     # escucha en :8099, POST /make-video
   ```
   Env del host: `ANTHROPIC_API_KEY`, `RUNPOD_API_KEY`, claves OpenAI/ElevenLabs.
2. **En el nodo HTTP "Disparar studio.py make":** poner la URL pública del endpoint
   (`https://TU-HOST:8099/make-video`) y crear la credencial *Header Auth* con
   Name=`X-Auth-Token`, Value=`<secreto>` (el mismo `STUDIO_TOKEN`).

Contrato HTTP del endpoint (idéntico al del webhook): `POST /make-video` con
`{slug, brief, max_cost, approve?}` → `200 {ok:true,...}` vídeo · `422 {ok:false,...}`
PARADA (coste/assets) · `400` petición inválida · `401` token incorrecto. `GET /health`
para liveness. Como `make` tarda minutos (GPU), el nodo HTTP usa timeout de 60 min.

## Importar el workflow (self-hosted, Execute Command)

`n8n/workflow.json` es un workflow **importable**: en n8n → *Workflows → Import from
File* → elige `n8n/workflow.json`. Nodos:

1. **Webhook (POST `make-video`)** — recibe `{slug, brief, max_cost, approve?}` en el body.
2. **Execute Command** — corre `studio_webhook.py` en el host del runner:
   `cd ${REPO_DIR:-/workspace/instalacion-confy} && python3 studio_webhook.py '{{ JSON.stringify($json.body) }}'`
3. **IF `ok`** — `true` (vídeo) → responde 200; `false` (PARADA coste/assets) → responde 422
   con el plan/log. n8n decide notificar y, para aprobar, reenvía el webhook con
   `"approve": true`.

**Setup del runner** (host donde corre el Execute Command):
- Define `REPO_DIR` apuntando al repo clonado (o edita el comando).
- Env: `ANTHROPIC_API_KEY`, `RUNPOD_API_KEY`, claves ElevenLabs/OpenAI.
- El nodo Execute Command exige que n8n tenga acceso shell a ese host (self-hosted
  n8n, o un nodo SSH al runner).

**Briefs con apóstrofes:** el comando por defecto pasa el JSON entre comillas simples.
Si tus briefs llevan `'`, usa la variante **base64** (sin problemas de comillas):
`... python3 studio_webhook.py --b64 {{ Buffer.from(JSON.stringify($json.body)).toString('base64') }}`

## Notificaciones (opcional, añádelas tú)

- **PARADA 2 (coste)** → Slack/email con el coste + botón que reenvía con `approve:true`.
- **PARADA 1 (assets)** → notifica la lista exacta de archivos a aportar.
- **OK** → publica/avisa con `outputs_dir`.

## Requisitos del runner/pod

- Repo clonado + `pip install -r` (anthropic, jsonschema, requests, websocket-client).
- Env: `ANTHROPIC_API_KEY` (creatividad), `RUNPOD_API_KEY` (pod GPU),
  claves de ElevenLabs/OpenAI (voz/imagen in-pod). `make` enciende el pod solo
  durante el lote y lo apaga al terminar (fases A→J).

> Nota: la fase GPU end-to-end de `produce` (render de clips frescos) se completa en
> una iteración aparte; hoy `make` ejecuta brief→pieza→fill→gate→montaje y reutiliza
> clips presentes. El contrato del webhook no cambia cuando se complete esa fase.
