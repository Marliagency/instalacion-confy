# Producción QYRO — 5 vídeos estilo Nike (app de hábitos con IA)

> Estado: **PREPARADO, sin renderizar.** El pipeline RunPod/ComfyUI está bloqueado
> por la red de esta sesión (`host_not_allowed` en `api/rest.runpod.io` y el proxy).
> Estos archivos quedan listos para renderizar de un tirón en cuanto se desbloquee
> `*.proxy.runpod.net` (Settings del entorno → Network access = Custom → sesión nueva).

## Concepto

Anuncio dinámico y motivador, **estilo Nike**: un solo protagonista (hombre
atlético) recorriendo un día de disciplina wellness — despertar, entrenar,
hidratarse, comer bien, salir a por sus objetivos. Tono: imperativo, épico,
"no excuses". La app **QYRO** aparece como el sistema que ordena ese día.

## ⚠️ Regla innegociable: la app NO se toca

La IA (WAN / cualquier t2v) **no puede reproducir tu UI real pixel a pixel** — se
inventaría una interfaz falsa. Por eso los 5 clips de IA muestran SOLO al avatar y
el lifestyle (sin pantallas de app: ver `app interface, phone screen ui` en el
prompt negativo). **La app se añade en el montaje por COMPOSICIÓN**: encima del
clip se incrusta tu **captura real** (en un mockup de móvil o como inserto a
pantalla). Así QYRO sale exactamente como es, intacta.

## Ficha del avatar (consistencia en los 5 clips)

Hombre atlético, finales de los 20, pelo corto oscuro, barba ligera, complexión
magra y musculada, piel tono medio cálido, ropa deportiva minimalista en negro/
carbón, expresión decidida y serena. (Esta descripción va clavada al inicio de
cada prompt para mantener el mismo personaje. Para consistencia perfecta entre
clips, lo ideal cuando rendericemos es generar un fotograma de referencia y usar
i2v, o fijar la misma `seed`.)

## Los 5 clips + mapa de composición

Cada clip: 9:16, 480×832, 81 frames (~5s a 16fps). Orden de montaje sugerido =
orden de la lista. Texto en pantalla en **español**, tipografía bold, animación
de entrada rápida (estilo Nike).

| # | id | Escena IA | Captura real superpuesta | Copy en pantalla |
|---|----|-----------|--------------------------|------------------|
| 1 | `qyro01_despertar` | Despierta antes del alba y se levanta decidido | **Hábitos** (checklist del día + racha "2 días", 3/7 hechos) | "Hoy no se negocia." |
| 2 | `qyro02_gimnasio` | Levantamiento pesado explosivo, sudor, garra | **Entrenamientos · Progreso** (sugerencias, "Atascados", Press de banca) | "El progreso no descansa." |
| 3 | `qyro03_hidratacion` | Bebe agua y respira tras entrenar | **Nutrición · Hoy** (Agua 5/8 vasos, Foto con IA) | "Cuida la máquina." |
| 4 | `qyro04_nutricion` | Cocina sano y fotografía el plato con el móvil | **Nutrición · Alimentos** (planes por objetivo) + gesto "Foto con IA" | "Come para ganar." |
| 5 | `qyro05_manifiesto` | Corre al amanecer y se planta mirando al frente | Cierre de marca **QYRO** + montaje rápido de todas las pantallas | "QYRO. Conviértete en tu mejor versión." |

### Detalle de composición por clip
- **Clip 1:** el inserto de Hábitos entra cuando se pone de pie (mockup de móvil
  en mano o inserto lateral). El check de un hábito coincide con un golpe de música.
- **Clip 2:** Entrenamientos · Progreso como inserto de pantalla a ~media duración;
  resalta la sugerencia "Añade 1 rep" sincronizada con la repetición.
- **Clip 3:** anillo/contador de Agua 5/8 entra al beber; el "+" de vasos se anima.
- **Clip 4:** cuando levanta el móvil para fotografiar el plato, encajar ahí la
  pantalla real de "Foto con IA" (la app detecta la comida) — momento héroe del IA.
- **Clip 5:** sin UI durante la carrera; al final, tarjeta negra con logo **QYRO**
  y montaje veloz (0.2s c/u) de las 4 capturas reales.

## Música / ritmo
Pista percutiva in crescendo (BPM ~120-140), cortes al beat, último clip con
caída/drop en el plano final + aparición del logo. Voz en off opcional (es-ES),
tono breve e imperativo.

## Coste estimado del render (cuando se desbloquee)
5 clips de vídeo WAN en una RTX 4090 (Spot/Community). A ~3-6 min/clip ≈
**15-30 min de GPU**. A ~$0.40-0.70/h de 4090 spot → **≈ $0.10-0.35** de GPU.
(El H100 del pod actual es ~$3/h: preferir 4090/3090 en EUR-IS-1 al rearrancar.)

## Cómo renderizar (sesión nueva con red desbloqueada)

1. `python3 runpod_ctl.py start gy9p9fryeh1yex --wait-comfy`
2. Construir el `workflows/wan_t2v.json` real (loaders WAN del pod) e iterar
   contra `/prompt` hasta validar.
3. Render del lote:
   ```bash
   python3 comfy_batch.py \
       --comfy-url https://gy9p9fryeh1yex-8188.proxy.runpod.net \
       --prompts ./batch_prompts.json \
       --out ./outputs \
       --workflow-video ./workflows/wan_t2v.json
   ```
4. Descargar de `./outputs`, **componer** las capturas reales según la tabla, y
   **APAGAR** el pod: `python3 runpod_ctl.py stop gy9p9fryeh1yex`.

Validación sin GPU (ya pasada): `python3 comfy_batch.py --dry-run --prompts
./batch_prompts.json --workflow-video ./workflows/wan_t2v.template.json`
