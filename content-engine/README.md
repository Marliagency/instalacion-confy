# 🎬 Content Engine — producción semanal a escala

Genera **100+ vídeos cortos por semana**. **ComfyUI** crea las imágenes (solo
tiempo de GPU) y **ffmpeg** las convierte en vídeos con movimiento, transiciones,
titular y audio. Pensado para orquestarse desde **Claude Code**.

```
plan semanal ─► (expand) ─► prompts ─► (ComfyUI) ─► frames ─► (ffmpeg) ─► 100+ vídeos
   (datos)                              multi-GPU            paralelo
```

## La idea para escalar: plantillas, no briefs

No escribes 100 briefs. Defines unas pocas **plantillas** (producto, tip,
testimonio…) y un **plan semanal** con los datos. El expansor los combina y
produce las N piezas de forma determinista. Subir volumen = añadir líneas al plan.

| Capa | Qué es | Quién la toca |
|------|--------|---------------|
| **Marcas** (`marcas/`) | Estilo visual + workflow de ComfyUI por marca | 1 vez |
| **Plantillas** (`plantillas/`) | Estructura de tomas con variables `{...}` | 1 vez |
| **Plan** (`semanas/<W>/plan.json`) | Los datos de la semana | Cada semana |
| **Manifiesto** (`manifest.json`) | Estado de cada pieza | Automático |

## Reparto con Claude Code

- **Claude Code (cerebro):** lee los briefs de la empresa y escribe el `plan.json`
  de la semana. Luego lanza el pipeline.
- **El motor (manos):** expande, genera en ComfyUI y edita con ffmpeg, de forma
  determinista, paralela y tolerante a fallos.

## Estructura

```
content-engine/
├── new_week.py             # crea una semana (+ ejemplos la 1ª vez)
├── engine/
│   ├── expand.py           # plan + plantillas -> manifiesto (N piezas)
│   ├── generate.py         # frames con ComfyUI (multi-GPU, reintentos)
│   ├── edit.py             # vídeo con ffmpeg (paralelo, titular, multi-formato)
│   ├── pipeline.py         # orquestador (--simular / --reintentar)
│   ├── plan_organico.py    # intención -> plan equilibrado + calendario
│   ├── dashboard.py        # tablero web (sin dependencias)
│   └── comfy.py · common.py
├── marcas/<marca>/
│   ├── estilo.json         # variables de estilo de la marca
│   ├── workflow.json       # workflow de ComfyUI (formato API)  ← lo exportas tú
│   └── workflow.map.json   # IDs de nodo prompt/seed/resolución
├── plantillas/*.json       # producto, tip, testimonio, dato, tutorial…
├── pilares.json            # pilares orgánicos (peso + plantillas + hooks)
└── semanas/<W>/
    ├── plan.json           # INPUT de la semana
    ├── intencion.json      # INPUT del flujo orgánico (opcional)
    ├── manifest.json       # estado (autogenerado)
    ├── calendario.csv      # calendario orgánico (autogenerado)
    ├── inputs/audio/       # audio opcional por pieza  (<id>.mp3, …)
    ├── generated/          # frames + clips intermedios
    └── edited/<formato>/   # VÍDEOS FINALES
```

## Máquina de estados (resumable y tolerante a fallos)

```
plan ─► prompt ─► generado ─► final
                     └────────► error   (un fallo NO tumba el lote)
```

Cada pieza avanza sola. Si una falla (timeout de ComfyUI, OOM…) queda en `error`
con su mensaje y el resto continúa. `--reintentar` reanuda solo las fallidas, y si
ya tenían frames no regasta GPU.

## Uso

```bash
# 1. Crear la semana (la 1ª vez crea marca y plantillas de ejemplo)
python3 new_week.py 2026-W23

# 2. (1ª vez) Exporta tu workflow de ComfyUI en "formato API"
#    (Settings → Dev mode → Save API Format) como marcas/default/workflow.json
#    y pon en workflow.map.json el ID del nodo de texto y del KSampler.

# 3. Edita semanas/2026-W23/plan.json con los items de la semana,
#    o pide a Claude Code: "lee los briefs y genera el plan de esta semana".

# 4. PROBAR el flujo sin gastar GPU (frames de color de prueba):
python3 engine/pipeline.py 2026-W23 --simular

# 5. Producción real:
python3 engine/pipeline.py 2026-W23

# 6. Reanudar lo que haya fallado:
python3 engine/pipeline.py 2026-W23 --reintentar

# Tablero de progreso (otra terminal):
python3 engine/dashboard.py        # http://localhost:8800
```

## Formato del plan

```json
{
  "config": {
    "formatos": ["9:16", "1:1"],
    "duracion_toma": 3.5, "fps": 30, "transicion": 0.5,
    "reintentos": 2,
    "hosts": ["127.0.0.1:8188", "127.0.0.1:8189"],
    "editores": 4
  },
  "items": [
    {"template": "producto", "marca": "default",
     "vars": {"producto": "Zapatilla Aera", "titular": "Nueva Aera", "cta": "Compra ya"}},
    {"template": "tip", "marca": "default",
     "vars": {"tema": "running", "idea": "calienta 5 min", "titular": "Tip runner", "cta": "Síguenos"}}
  ]
}
```

Campos por item: `template` (nombre en `plantillas/`), `marca`, `vars` (rellenan
los `{...}` de la plantilla), y opcionalmente `id`, `titular`, `cta`, `canal`,
`dia`, `formatos`, `audio`, `seed_base`.

## Palancas de escala

| Quieres… | Haces… |
|----------|--------|
| Más throughput de generación | Añade instancias de ComfyUI a `hosts` (una por GPU); se reparten solas |
| Editar más rápido | Sube `editores` (procesos ffmpeg en paralelo) |
| Más formatos por vídeo | Añade a `formatos`: `9:16`, `1:1`, `16:9`, `4:5` |
| Estilos distintos por marca | Crea `marcas/<otra>/` con su `workflow.json` y `estilo.json` |
| Más tipos de contenido | Añade plantillas en `plantillas/` |

A modo de referencia: 100 vídeos ≈ 300 imágenes ≈ **menos de 2 h en 1 GPU**, y la
edición corre en paralelo después (o mientras la GPU sigue).

## Contenido orgánico

Reparte el volumen entre **pilares** (educar, entretener, inspirar, comunidad) y un
**calendario** por día y canal. Cada pilar tiene un **peso** (mezcla objetivo) y sus
plantillas hook-first. Los canales (`tiktok`, `ig-feed`, `youtube`…) se mapean a su
formato automáticamente.

```bash
# 1. Escribe la intención de la semana (Claude Code la genera desde tu estrategia)
#    semanas/<W>/intencion.json:  total, canales, temas, mezcla de pilares
# 2. Planifica: reparte por pilares + asigna canal, formato y día
python3 engine/plan_organico.py 2026-W24
#    -> genera plan.json equilibrado + calendario.csv
# 3. Produce (mismo motor)
python3 engine/pipeline.py 2026-W24 --simular   # o sin --simular para real
```

`intencion.json`:

```json
{
  "marca": "default",
  "total": 24,
  "canales": ["tiktok", "ig-feed", "youtube"],
  "temas": ["sentadilla correcta", "proteína", "descanso", "movilidad"],
  "mezcla": {"educar": 0.4, "entretener": 0.3, "inspirar": 0.2, "comunidad": 0.1}
}
```

El planificador reparte las piezas por pilar (método del mayor resto), asigna canal
y día, le pone un hook automático y escribe un **calendario.csv** (día · canal ·
pilar · titular). El tablero muestra ese calendario por semana.

## Ampliaciones

- **Vídeo generativo real:** un `generate.py` alterno con workflow AnimateDiff/SVD/
  WAN; el resto del pipeline no cambia.
- **Texto multilínea / lower-thirds animados:** ampliar el bloque `drawtext` en `edit.py`.
- **Aprobación humana:** añadir una fase `revisión` antes de `final`.
- **Publicación:** un `publish.py` que suba los `edited/` a cada plataforma.

## Requisitos

- Python 3.8+ — **solo librería estándar, cero pip installs**
- `ffmpeg` en el PATH (con una fuente DejaVu para los titulares)
- ComfyUI corriendo (una o varias instancias) — salvo en modo `--simular`
