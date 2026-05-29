# Pipeline de producción en masa (imágenes y video): RunPod + ComfyUI + Claude Code

Das un brief → Claude Code expande el lote de prompts → enciende una GPU en la
nube → genera todas las **imágenes y/o videos** → te los descarga → apaga la GPU.

**Coste objetivo:** lo más cerca de cero posible. Solo pagas los minutos de GPU
encendida (~$0.34–0.39/hora una RTX 4090) más el almacenamiento del Network
Volume (~$5–10/mes por 100 GB).

```
   TÚ (brief general)
        │
        ▼
   CLAUDE CODE ──(MCP RunPod)──► enciende/apaga el pod GPU
        │
        │  expande el brief en N prompts
        ▼
   SCRIPT PUENTE (comfy_batch.py) ──(API HTTP)──► ComfyUI en el pod
        │                                              │ genera los videos
        ◄──────────── descarga los .mp4 ──────────────┘
        ▼
   TU MAC (carpeta ./outputs con todos los videos + reporte de coste)
```

Claude Code controla el encendido/apagado y la expansión del brief. El script
puente (`comfy_batch.py`) es quien realmente manda los prompts a ComfyUI y
descarga los resultados.

---

## Qué hay en este repo

| Archivo | Para qué sirve |
|---|---|
| `CLAUDE.md` | Reglas de orquestación. Claude Code lo lee solo y controla coste, encendido/apagado y expansión del brief. |
| `comfy_batch.py` | Script puente: inyecta cada prompt en ComfyUI, espera y descarga los archivos (`.mp4` video / `.png` imagen). Soporta `--dry-run`. |
| `workflows/sdxl_t2i.json` | Workflow de **imágenes** (SDXL). Usable casi tal cual (solo ajusta el checkpoint). |
| `workflows/wan_t2v.template.json` | Plantilla del workflow de **video** (WAN). La reemplazas por tu export real. |
| `workflows/README.md` | Cómo ajustar/exportar cada workflow. |
| `requirements.txt` | Dependencias del script puente (`requests`, `websocket-client`). |
| `batch_prompts.example.json` | Ejemplo del formato de prompts (mezcla imagen + video). |
| `.gitignore` | Evita subir videos generados y secretos. |

> El pipeline **se ejecuta desde tu Mac** (donde tienes Claude Code, tu cuenta de
> RunPod y donde quieres recibir los videos). Este repositorio solo aloja los
> archivos del pipeline; clónalo en tu Mac para usarlo.

---

## Requisitos previos (una sola vez)

1. **Node.js 18+** (para el MCP de RunPod). Comprueba: `node --version`. Si no lo
   tienes, instala la versión LTS desde <https://nodejs.org>.
2. **Python 3.9+** (para el script puente). Comprueba: `python3 --version`.
3. **Cuenta en RunPod + saldo** ($10 sobra para empezar):
   - Regístrate en <https://runpod.io>
   - Carga $10
   - Settings → API Keys → crea una key. **Cópiala.**
4. **Claude Code** instalado y funcionando en tu Mac.

---

## Instalación (en tu Mac)

### Paso 0 — Clonar este repo e instalar dependencias del script

```bash
git clone https://github.com/marliagency/instalacion-confy.git
cd instalacion-confy
pip3 install -r requirements.txt
```

> En cualquier momento puedes ejecutar `python3 check_setup.py` para que te diga
> qué te falta (Python, dependencias, Node, la API key y los workflows).

### Paso 1 — Guardar la API key de RunPod

```bash
echo 'export RUNPOD_API_KEY="pega_tu_key_aqui"' >> ~/.zshrc
source ~/.zshrc
echo $RUNPOD_API_KEY   # debe mostrar tu key
```

### Paso 2 — Conectar el MCP de RunPod a Claude Code

```bash
claude mcp add runpod -s user \
  -e RUNPOD_API_KEY=$RUNPOD_API_KEY \
  -- npx -y @runpod/mcp-server@latest
```

Verifica:

```bash
claude mcp list   # debe aparecer "runpod"
```

Si ya estás en una sesión activa de Claude Code, escribe `/mcp` para reconectar
sin reiniciar. Con esto, Claude Code ya puede crear, arrancar, parar y borrar
pods por ti.

### Paso 3 — Crear un Network Volume (almacenamiento persistente)

> **IMPORTANTE:** sin esto, cada vez que apagas el pod pierdes los modelos
> descargados (varios GB) y tendrías que volver a bajarlos (lento y pagando ese
> tiempo). El Network Volume guarda ComfyUI + los modelos WAN de forma
> permanente, y solo cuesta ~$0.05–0.10/GB al mes (100 GB ≈ $5–10/mes).

Pídeselo a Claude Code:

```
Crea un network volume en RunPod de 100GB en el datacenter más barato
disponible y dime el ID cuando esté listo.
```

O hazlo manual en la consola web: Storage → Network Volumes → New Volume →
100 GB → Secure Cloud. **Anota el `VOLUME_ID`** (lo necesitas en el Paso 4).

### Paso 4a — Primer arranque del pod con la plantilla WAN (una vez)

Plantilla recomendada (la más completa para WAN):
**"One Click ComfyUI - Wan 2.1 / Wan 2.2 (CUDA 12.8)" de HearmemanAI**
(búscala en el RunPod Hub / marketplace de plantillas). Soporta text-to-video,
image-to-video, video-to-video, Wan VACE y Wan Fun.

La PRIMERA vez, el pod descarga ComfyUI + modelos al network volume. Conviene
hacerlo con una GPU barata para no pagar de más. Pídeselo a Claude Code:

```
Arranca un pod en RunPod con:
- Plantilla: la de ComfyUI Wan 2.2 de HearmemanAI (pásame opciones si hay varias)
- GPU: la más barata disponible (RTX 3090 si está)
- Network volume: [VOLUME_ID del paso 3]
- Puerto expuesto: 8188 (ComfyUI) y 8888 si la plantilla usa Jupyter
Cuando esté "running", dame la URL pública del puerto 8188.
```

Abre la URL del puerto 8188 en tu navegador para confirmar que ComfyUI arranca
(la primera descarga de modelos puede tardar). Cuando confirmes que funciona:

```
Para (stop) el pod actual de RunPod para no seguir pagando.
```

Con `stop`, el network volume conserva todo; solo dejas de pagar la GPU.

### Paso 4b — Preparar los workflows (una vez)

ComfyUI **no genera desde texto plano**: necesita un *workflow* (grafo de nodos)
en formato API. Hay uno por tipo de salida, en la carpeta `workflows/`.

**Imágenes (`workflows/sdxl_t2i.json`)** — ya incluido y usable. Único ajuste:
abre el archivo y, en el nodo `4` (`CheckpointLoaderSimple`), pon en `ckpt_name`
el nombre exacto del checkpoint SDXL instalado en tu pod (lo ves en el desplegable
"Load Checkpoint" de la UI de ComfyUI).

**Video (`workflows/wan_t2v.json`)** — debes exportarlo tú una vez:

1. Con el pod encendido, abre ComfyUI (puerto 8188).
2. Carga un workflow WAN **text-to-video** y genera UN video de prueba.
3. Ajustes (engranaje) → activa **"Enable Dev mode Options"** → aparece el botón
   **"Save (API Format)"**.
4. Pulsa **Save (API Format)** y guarda el archivo como `workflows/wan_t2v.json`.

El script localiza automáticamente el nodo de prompt positivo/negativo (siguiendo
los enlaces del sampler), la semilla, la resolución y el nº de fotogramas, e
inyecta los valores de cada item. Valida que tu workflow es compatible sin gastar
GPU:

```bash
python3 comfy_batch.py --dry-run \
  --prompts ./batch_prompts.example.json \
  --workflow-image ./workflows/sdxl_t2i.json \
  --workflow-video ./workflows/wan_t2v.json
```

---

## Producción: el flujo cerrado

En cada sesión de producción, abre Claude Code en esta carpeta y di algo como:

```
Lee CLAUDE.md. Quiero 40 videos variando este brief:
"[tu brief general aquí]". Estilo cinematográfico, 9:16, 5 segundos cada uno.
Encárgate de todo: enciende el pod, genera el lote y devuélveme los videos.
```

O para imágenes:

```
Lee CLAUDE.md. Quiero 30 imágenes verticales 9:16 sobre este brief:
"[tu brief]". Encárgate de todo y devuélveme los archivos.
```

Puedes mezclar: "20 imágenes y 10 videos sobre …".

Claude Code hará automáticamente:

1. Expandir tu brief en N prompts distintos (`batch_prompts.json`), marcando cada
   uno como imagen o video.
2. Mostrarte 3-5 prompts de ejemplo + coste estimado y esperar tu OK.
3. Arrancar el pod (`start`, ya no re-descarga nada) y esperar a ComfyUI.
4. Ejecutar `comfy_batch.py` con los prompts.
5. Descargar los archivos a `./outputs/` (`.mp4` video / `.png` imagen).
6. **APAGAR el pod.**
7. Darte el reporte: nº de archivos, tiempo y coste estimado.

### Ejecución manual del script (si la quieres lanzar tú)

```bash
python3 comfy_batch.py \
  --comfy-url https://XXXX-8188.proxy.runpod.net \
  --prompts ./batch_prompts.json \
  --out ./outputs \
  --workflow-video ./workflows/wan_t2v.json \
  --workflow-image ./workflows/sdxl_t2i.json
```

---

## Control de coste (crítico)

- El pod cobra **por minuto encendido**, no por video. Regla de oro: **nunca
  dejes un pod en "running" sin generar.**
- `CLAUDE.md` obliga a Claude a apagar el pod al terminar el lote y a avisarte si
  detecta un pod encendido ocioso.
- Pon una alerta de gasto en RunPod: Settings → Billing → spending limit.
- Revisa en la consola de RunPod que no queden pods "running" al final del día.

---

## Resolución / límites (expectativas realistas)

- **RTX 4090 (24 GB):** modelos WAN 14B a 480p, o el modelo TI2V-5B a 720p.
- Para 720p estable en modelos grandes necesitarías A100/H100 (más caros).
- Para redes (9:16 vertical, móvil) 480–720p suele ser suficiente; puedes hacer
  upscaling después si lo necesitas.
