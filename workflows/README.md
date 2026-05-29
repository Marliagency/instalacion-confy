# Workflows de ComfyUI

`comfy_batch.py` necesita un *workflow* en **formato API** (un grafo de nodos)
por cada tipo de salida. Aquí viven esos workflows.

| Archivo | Tipo | Estado |
|---|---|---|
| `sdxl_t2i.json` | Imagen (SDXL text-to-image) | **Usable casi tal cual.** Solo ajusta el nombre del checkpoint. |
| `wan_t2v.template.json` | Video (WAN text-to-video) | **Plantilla.** Debes reemplazarla por tu export real (ver abajo). |

## Imágenes — `sdxl_t2i.json`

Workflow SDXL estándar (Checkpoint → CLIPTextEncode pos/neg → EmptyLatentImage →
KSampler → VAEDecode → SaveImage), a 832×1216 (vertical 9:16).

**Único ajuste necesario:** en el nodo `4` (`CheckpointLoaderSimple`), cambia
`ckpt_name` por el nombre exacto del checkpoint SDXL que tengas instalado en el
pod (míralo en la UI de ComfyUI, en el desplegable del nodo "Load Checkpoint").

El script inyecta automáticamente: prompt positivo, prompt negativo, semilla
(aleatoria por item salvo que la fijes), y `width`/`height` si los pones en el item.

## Video — exporta tu `wan_t2v.json` real

Los nodos y nombres de modelo de WAN dependen de los modelos concretos de tu pod,
por eso **no** se incluye un workflow de video "que funcione" (uno inventado te
rompería la generación). Hazlo una vez:

1. Con el pod encendido, abre ComfyUI (puerto 8188).
2. Carga un workflow WAN **text-to-video** y genera UN video de prueba para
   confirmar que funciona end-to-end.
3. Engranaje (ajustes) → activa **"Enable Dev mode Options"**.
4. Pulsa el botón **"Save (API Format)"** y guarda el archivo como
   `workflows/wan_t2v.json` en este proyecto.

`wan_t2v.template.json` solo sirve para que `comfy_batch.py --dry-run` valide que
el script detecta bien los nodos (positivo, negativo, semilla, resolución,
fotogramas). No la uses para generar.

## Comprobar que un workflow es compatible con el script

```bash
python3 comfy_batch.py --dry-run \
  --prompts ../batch_prompts.example.json \
  --workflow-image ./sdxl_t2i.json \
  --workflow-video ./wan_t2v.template.json
```

Debe listar, por cada item, el nodo positivo/negativo detectado, la semilla y el
prompt inyectado. Si algún item da error de detección, ajusta las heurísticas en
`find_prompt_nodes()` dentro de `comfy_batch.py`.
