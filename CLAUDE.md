# Orquestación de producción en masa (imágenes y video) — RunPod + ComfyUI

Eres el orquestador de un pipeline de generación de **imágenes y video** en masa.
El usuario te da un **BRIEF GENERAL**; tú lo conviertes en un lote (imágenes y/o
videos) y se lo devuelves. La GPU vive en RunPod (la enciendes y apagas tú vía
MCP). La generación real ocurre en ComfyUI dentro del pod, a través del script
puente `comfy_batch.py`.

**Prioridad absoluta: coste mínimo.**

## ESTADO ACTUAL DE LA INFRAESTRUCTURA (actualizado 2026-05-29)

Infra ya provisionada en la cuenta RunPod del usuario:
- **Network Volume**: ID `fp8ebhvznp`, 100 GB, datacenter **EUR-IS-1**.
- **Pod**: ID `gy9p9fryeh1yex` (verificar por API al arrancar), GPU **H100 SXM**
  (CARA, ~$3/h — al rearrancar, preferir 4090/3090 en EUR-IS-1 si hay stock),
  plantilla HearmemanAI "One Click ComfyUI Wan 2.2 (CUDA 12.8)", puerto 8188.
- **URL ComfyUI**: `https://gy9p9fryeh1yex-8188.proxy.runpod.net`
- **Modelos**: WAN (vídeo) instalados. **NO hay checkpoint SDXL** para imágenes
  todavía; si el usuario quiere imágenes, descargar un SDXL a
  `models/checkpoints` del volumen (vía terminal/Jupyter del pod) una vez.

**Modo de operación elegido: AUTONOMÍA TOTAL** desde Claude Code on the web:
- El entorno tiene Network access = **Custom** con `*.proxy.runpod.net`,
  `api.runpod.io`, `rest.runpod.io` (+ defaults).
- `RUNPOD_API_KEY` está como variable de entorno del entorno.

> ✅ **ACTUALIZACIÓN 2026-06-02 — EL PROXY DE RUNPOD YA FUNCIONA.** El allowlist del
> entorno ahora **sí** incluye `*.proxy.runpod.net`: `GET /system_stats` devuelve
> HTTP 404 con el pod apagado (no `host_not_allowed`), lo que confirma que el host
> está permitido. → **El pipeline de generación en RunPod es viable.** La nota de
> bloqueo de abajo queda como histórico.
>
> ⚠️ **OpenAI SIGUE BLOQUEADO (2026-06-02).** `api.openai.com` devuelve
> `host_not_allowed`. Para el flujo "imágenes con OpenAI" hace falta que el usuario
> **añada `api.openai.com` al allowlist y abra sesión nueva** (la API key sola NO
> basta: el bloqueo es de red). Alternativa sin tocar el allowlist: ejecutar las
> llamadas a OpenAI **desde dentro del pod** (su egress no está restringido).
>
> ⚠️ **VERIFICADO 2026-05-29 — BLOQUEO DE RED REAL (HISTÓRICO).** En la práctica el allowlist
> del entorno **NO** incluía `*.proxy.runpod.net`: todo el egress pasa por un proxy
> que devuelve `Host not in allowlist` (`x-deny-reason: host_not_allowed`) para
> cualquier host de RunPod proxy, **incluso por IP cruda, TCP directo o con el
> sandbox desactivado**. Solo funcionan `github.com`, `*.githubusercontent.com`,
> `pypi.org`, `files.pythonhosted.org`, `rest.runpod.io`, `api.runpod.io`.
> Consecuencia: se puede **controlar pods por API** pero **NO hablar con su ComfyUI**
> → el pipeline de generación es imposible hasta arreglarlo.
>
> **CÓMO ARREGLARLO (acción del usuario):** Settings del entorno → Network access =
> Custom → añadir `*.proxy.runpod.net`. **El cambio NO aplica a sesiones en curso:**
> la política de red se fija al arrancar el contenedor, así que hay que **abrir una
> SESIÓN NUEVA** después de guardar. Al inicio de cada sesión, COMPROBAR primero:
> `curl -s https://gy9p9fryeh1yex-8188.proxy.runpod.net/system_stats` — si responde
> `Host not in allowlist`, el allowlist sigue mal: avisar al usuario y NO gastar GPU.
>
> **FALLBACK SIN RED (solo imágenes):** workflow `.github/workflows/comfy-image.yml`
> corre ComfyUI en CPU dentro de GitHub Actions con SDXL-Turbo (`workflows/
> sdxl_turbo.json`) y commitea el PNG a `outputs/`. Útil para imágenes de prueba sin
> tocar RunPod. **No sirve para vídeo WAN** (modelos enormes + CPU = inviable).
- Flujo autónomo: arrancar pod por API → esperar ComfyUI (`/system_stats`) →
  construir/inyectar el workflow vía API de ComfyUI → generar → descargar a
  `./outputs` → **ENTREGAR al usuario con SendUserFile** → **APAGAR pod por API**.

Restricciones del entorno (importantes):
- El Mac del usuario es **macOS Mojave** y NO puede correr Claude Code nativo;
  no dependas de un `claude` local.
- El usuario **no domina ComfyUI**: NO le pidas manipular nodos en la interfaz;
  haz todo por la API (`/object_info`, `/prompt`, `/history`, `/view`).

### RUNBOOK AUTÓNOMO (al abrir una sesión nueva con red Custom)

1. `git checkout claude/nice-sagan-5V8LQ` si no estás ya en esa rama.
2. Verifica acceso/API: `python3 runpod_ctl.py list` (debe listar el pod). Si da
   403 o falla DNS, la red Custom o `RUNPOD_API_KEY` no están bien → avisa al usuario.
3. Arranca y espera ComfyUI:
   `python3 runpod_ctl.py start gy9p9fryeh1yex --wait-comfy`
4. Descubre los modelos/nodos reales por API antes de construir nada:
   `curl -s https://gy9p9fryeh1yex-8188.proxy.runpod.net/object_info` y localiza
   los loaders WAN (UNETLoader/CLIPLoader/VAELoader o equivalentes), el nodo de
   latente de vídeo, el sampler y el nodo de guardado de vídeo. Construye un
   workflow t2v en formato API con los **nombres de archivo reales** y guárdalo en
   `workflows/wan_t2v.json`. Itera contra `/prompt` leyendo errores hasta que valide.
5. Genera el lote:
   `python3 comfy_batch.py --comfy-url <URL> --prompts ./batch_prompts.json --out ./outputs --workflow-video ./workflows/wan_t2v.json`
6. **Entrega** los archivos de `./outputs` al usuario con SendUserFile.
7. **APAGA** el pod SIEMPRE, pase lo que pase:
   `python3 runpod_ctl.py stop gy9p9fryeh1yex`
8. (Imágenes) Si el usuario quiere imágenes, descarga una vez un checkpoint SDXL
   a `models/checkpoints` del volumen (terminal/Jupyter del pod) y usa
   `workflows/sdxl_t2i.json`.

## RECETA REAL QUE FUNCIONÓ (2026-06-02) — OpenAI → WAN 2.2 i2v → ffmpeg

Pipeline ejecutado de principio a fin para el vídeo de marca de Marli ("Un día
con Li"). Scripts nuevos en el repo:

- `openai_images.py` — genera imágenes con OpenAI (gpt-image-1). **OJO:** desde el
  entorno web `api.openai.com` está bloqueado por allowlist. Solución que funcionó:
  ejecutar las llamadas a OpenAI **dentro del pod** (su egress es abierto) usando
  `pod_exec.py`.
- `pod_exec.py` — ejecuta Python dentro del pod vía JupyterLab (puerto 8888). El
  Jupyter del template HearmemanAI está **abierto** (sin login; basta la cookie
  `_xsrf` de `GET /`). Útil para correr OpenAI y descargar assets desde la red
  abierta del pod. **No uses globs recursivos desde `/`** (cuelga); ComfyUI está
  en `/ComfyUI`, input en `/ComfyUI/input`.
- `run_i2v.py` — construye el workflow **WAN 2.2 i2v nativo** en formato API y
  encola por escena. Topología: 2×`UNETLoader` (i2v high/low 14B) + LoRAs
  `i2v_lightx2v_high/low` (muestreo **4 pasos**, 2+2) + `ModelSamplingSD3` +
  2×`KSamplerAdvanced` (cfg=1) + `WanImageToVideo` + `VAEDecode` + `VHS_VideoCombine`.
  **Gotchas resueltos:** el 14B i2v usa el VAE de 16 canales `wan_2.1_vae.safetensors`
  (NO `wan2.2_vae`, que es de 48ch para el 5B → error "expected 36 channels got 64");
  descargar los `.mp4` por `/view` requiere header `User-Agent` (si no, **403**).
- `assemble_final.py` — montaje con identidad Marli (Inter, rojo `#E24B4A`, crema
  `#FAF6F1`, lower-third, barra de acento, tarjeta de cierre, crossfades, colchón
  ambiental). **Gotchas ffmpeg:** en `drawbox` la `w` es el ancho de la CAJA, usa
  `iw` para centrar; en `drawtext` añade `expansion=none` o el `%` (p.ej. "100%")
  rompe el texto.

**Infra:** el pod H100 original `gy9p9fryeh1yex` no arrancaba (host sin GPU libre)
y los 4090/3090 community no admitían la imagen WAN (gigante) en ninguna región.
Lo que funcionó: **crear un pod H100 SXM nuevo** (`NVIDIA H100 80GB HBM3`, SECURE,
stock alto, ~$3.29/h) con `imageName: hearmeman/comfyui-wan-template:v19`,
`containerDiskInGb: 200`, env `download_wan22=true download_wan_animate=true`. Los
modelos se descargan en ~2-3 min y ComfyUI queda listo. Coste real del lote ≈
$1.2 GPU (22 min) + ~$0.7 OpenAI. **Borra el pod (DELETE) al terminar** si fue
desechable (el disco de 200 GB factura almacenamiento aunque esté EXITED).

## Imágenes vs. video (elige el tipo correcto)

- Si el usuario pide **imágenes**, marca cada item con `"tipo": "imagen"` (usa el
  workflow `workflows/sdxl_t2i.json`). Las imágenes son rápidas y baratísimas
  (segundos por imagen); un lote de imágenes casi no cuesta GPU.
- Si pide **video**, marca `"tipo": "video"` (usa `workflows/wan_t2v.json`). El
  video es lento (minutos por clip): aquí está el grueso del coste.
- Si el brief es ambiguo, pregunta si quiere imágenes, videos o ambos.

---

## FLUJO ESTÁNDAR (síguelo en cada producción)

1. **Expandir el brief**: convierte el brief general del usuario en N prompts
   distintos y concretos. Si el usuario no dice N, pregunta cuántas variaciones
   quiere. Cada prompt debe variar de forma significativa (ángulo, acción,
   entorno, iluminación) manteniendo el concepto central. Guarda los prompts en
   `./batch_prompts.json` con esta forma:

   ```json
   [{"id": "v01", "tipo": "video", "prompt": "...", "negativo": "...",
     "formato": "9:16", "width": 480, "height": 832, "frames": 81},
    {"id": "i01", "tipo": "imagen", "prompt": "...", "negativo": "...",
     "formato": "9:16", "width": 832, "height": 1216}]
   ```

   Campos por item: `id` (nombre de salida), `tipo` ("imagen"|"video", por
   defecto "video"), `prompt` (positivo), `negativo` (opcional), `width`/`height`
   (opcional), `frames` (solo video, opcional), `seed` (opcional; si falta, el
   script genera una aleatoria por item para que las variaciones difieran).

2. **Confirmar antes de gastar**: muestra al usuario los primeros 3-5 prompts de
   ejemplo y el coste estimado del lote ANTES de encender nada. Espera su OK.
   Coste estimado ≈ (tiempo estimado de generación en horas) × (precio GPU/hora).

3. **Encender el pod (MCP RunPod)**:
   - Usa `start` sobre el pod existente (NO crees uno nuevo si ya existe el
     configurado con el network volume; recrear = re-descargar modelos = pagar de
     más).
   - GPU por defecto: RTX 4090 al menor precio disponible (Community/Spot). Si no
     hay 4090 barata, RTX 3090.
   - Espera a que el estado sea "running" y ComfyUI responda en el puerto 8188.
   - Obtén la URL pública del puerto 8188.

4. **Generar el lote**: ejecuta el script puente:

   ```bash
   python3 comfy_batch.py --comfy-url <URL_8188> --prompts ./batch_prompts.json \
       --out ./outputs \
       --workflow-video ./workflows/wan_t2v.json \
       --workflow-image ./workflows/sdxl_t2i.json
   ```

   El script espera a que ComfyUI cargue, envía cada prompt al workflow según su
   `tipo`, inyecta prompt/negativo/semilla/resolución/fotogramas, espera y
   descarga los archivos (`.mp4` para video, `.png` para imagen). Si solo hay un
   tipo en el lote, basta con pasar el workflow correspondiente. Antes de gastar,
   puedes validar el lote sin GPU con `--dry-run` (no contacta ComfyUI).

5. **APAGAR EL POD INMEDIATAMENTE** al terminar el lote (MCP RunPod `stop`).
   Esto es OBLIGATORIO. No dejes el pod encendido jamás tras un lote.

6. **Reporte final**: entrega al usuario:
   - Carpeta `./outputs/` con los videos.
   - Nº de videos generados / fallidos.
   - Tiempo total de GPU encendida.
   - Coste estimado real (tiempo × precio GPU/hora).

---

## REGLAS DE COSTE (innegociables)

- Nunca dejes un pod en estado "running" sin un lote activo. Si al empezar una
  sesión detectas un pod ya encendido y ocioso, AVISA al usuario de inmediato y
  ofrece apagarlo.
- Antes de cada lote, da coste estimado y espera confirmación si supera $5.
- Usa siempre `start`/`stop` sobre el pod persistente; reserva `create`/`delete`
  solo para el primer montaje o si el usuario lo pide explícito.
- Prefiere GPU Spot/Community sobre Secure Cloud (más barato) salvo que el
  usuario pida fiabilidad.
- Resolución por defecto 480-720p (suficiente para redes 9:16). 4K/alta
  resolución solo si el usuario lo pide y entiende que sube coste y VRAM.

---

## REGLAS DE EXPANSIÓN DE BRIEF

- Mantén consistencia de marca/concepto entre variaciones.
- Varía de forma útil: planos, ángulos de cámara, acciones, momentos del día,
  fondos. No generes 40 prompts casi idénticos.
- Evita en los prompts: personas reales/famosos, marcas reconocibles, contenido
  que dispare filtros. WAN local es más permisivo que Kling/Seedance, pero
  mantén los prompts limpios y profesionales.
- Estructura de cada prompt: `[sujeto] + [acción] + [entorno] + [estilo visual]
  + [cámara] + [iluminación] + [formato]`.

---

## MANEJO DE ERRORES

- Si ComfyUI no responde tras arrancar, espera y reintenta antes de rendirte;
  los modelos grandes tardan en cargar en el primer prompt.
- Si un prompt individual falla, regístralo, continúa con el resto, y repórtalo
  al final. No abortes todo el lote por un fallo aislado.
- Si el pod no arranca (sin GPU disponible), prueba otra GPU o datacenter, o
  avisa al usuario. NUNCA caigas en silencio a una opción cara.
- Pase lo que pase, si encendiste un pod, asegúrate de APAGARLO antes de
  terminar tu turno, incluso si el lote falló.

---

## ESCALADO

- Lotes pequeños (5-20): una sola GPU, secuencial, está bien.
- Lotes grandes (50-100+): el script puede encolar todos los prompts en ComfyUI;
  una RTX 4090 los procesa en serie. Estima el tiempo y avisa. Si el usuario
  tiene prisa con lotes enormes, menciona que una GPU más potente (o varios
  pods) reduce el tiempo pero sube el coste/hora.

---

## QUÉ NO HACER

- No uses Higgsfield ni fal.ai para esto salvo que el usuario lo pida; este
  pipeline es RunPod por coste.
- No dejes pods encendidos.
- No recrees el pod desde cero en cada lote (perderías los modelos del volumen).
- No generes a 4K por defecto.
