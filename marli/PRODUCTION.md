# Marli — Sistema de producción de anuncios verticales (ComfyUI / RunPod)

Produce anuncios verticales 9:16 de **30 s** combinando 4 formatos de vídeo IA,
con **variaciones de estilo y tiempo** parametrizables. La generación corre en un
pod de **RunPod con ComfyUI**; el montaje final (text cards, slideshow,
concatenación y mezcla de audio) corre donde ejecutes `comfy_generate.py` con
`ffmpeg`.

```
configs/<ad>.yaml ─► comfy_generate.py ─► ComfyUI (Wan/FLUX) ─► beats ─► ffmpeg ─► outputs/<ad>.mp4
```

## Estructura

```
marli/
├── PRODUCTION.md
├── comfy_generate.py            # orquestador (solo dep: pyyaml)
├── setup_comfy.sh               # setup ÚNICO del pod (custom nodes + modelos)
├── music.wav                    # pista de fondo (PLACEHOLDER, sustitúyela)
├── configs/
│   └── marli_v2.yaml            # un anuncio entero (6 beats)
├── comfy_workflows/             # 4 workflows en formato API (PLANTILLAS)
│   ├── cinematic_wan22.json
│   ├── ugc_wan22.json
│   ├── image_flux_dev.json
│   └── slideshow_flux_dev_batch5.json
├── fonts/
│   ├── DMSerifDisplay-Regular.ttf
│   └── SpaceGrotesk-Regular.ttf
└── outputs/                     # resultados (ignorado por git)
```

## Los 4 formatos

| Formato | Qué es | Modelo | Audio | Duración |
|---|---|---|---|---|
| **cinematic** | Plano cinematográfico, sin texto | Wan 2.2 14B T2V | música | 3/5/8 s |
| **ugc** | Persona hablando a cámara, look selfie | Wan 2.2 T2V (+lip-sync opc.) | voz (ElevenLabs/grabada) + música baja | 5/8 s |
| **textcard** | Fondo IA premium + texto nítido en post | FLUX.1 dev (fondo) | música | 5 s |
| **slideshow5** | N imágenes que cambian cada `slide_dur` | FLUX.1 dev × N | música + sting | 5 s |

Naming de salidas: `beat<n>_<type>_<id>.mp4` (p.ej. `beat1_cinematic_hook.mp4`).

## Variaciones (§ del documento maestro)

- **Estilo** (`style`): editorial · cinematic · handheld · studio · golden-hour · noir.
- **Cámara** (`camera`, solo vídeo): static · slow-push-in · slow-orbit · dolly-left/right · handheld.
- **Tiempo**: `dur` por beat (3/5/8/10); en slideshow `slide_dur` (0.5/1.0/1.5) — el nº de
  slides se ajusta para llenar el beat. `fps` 24 por defecto.
- **Seed**: entero (repetible) o `random` (variación distinta cada corrida → 3-4 takes).

Cada uno se puede fijar global (raíz del YAML) o por beat (el beat manda).

## Puesta en marcha

### 1. Pod de RunPod con ComfyUI (una sola vez)
Dentro del pod (terminal/Jupyter), instala nodos y modelos:
```bash
bash setup_comfy.sh          # clona custom nodes + baja FLUX y Wan 2.2
```
Comprueba los nombres EXACTOS de los archivos de modelo en
`<POD>-8188.proxy.runpod.net/object_info` y ajusta los workflows si difieren.

### 2. Exporta tus 4 workflows reales (recomendado)
Los JSON de `comfy_workflows/` son **plantillas**. Arma cada gráfico en la UI de
ComfyUI y expórtalo con **Save (API Format)**, sobrescribiendo el archivo. En cada
uno, pon el **título** de los dos `CLIPTextEncode` como `positive` y `negative`
(el orquestador los busca por título).

El orquestador parchea automáticamente en cada workflow:
- `CLIPTextEncode` *positive* → prompt + sufijo de estilo (+ frase de cámara en vídeo).
- `CLIPTextEncode` *negative* → `text, letters, logos, watermarks, distorted hands, blurry`.
- nodo `Empty*Latent*` → 1080×1920 (y `length = dur × fps` en vídeo).
- `KSampler.seed` → del config.

### 3. Genera un anuncio
```bash
export COMFY_HOST="https://<POD_ID>-8188.proxy.runpod.net"
export ELEVENLABS_KEY="..."        # solo si algún beat usa audio.source: tts
pip install pyyaml
python3 comfy_generate.py configs/marli_v2.yaml
# -> outputs/marli_v2/beat<n>_<type>_<id>.mp4  +  outputs/marli_v2.mp4 (final 30 s)
```

### Probar sin GPU (placeholders)
```bash
python3 comfy_generate.py configs/marli_v2.yaml --simular
```
Genera fondos/planos de color en vez de llamar a ComfyUI, pero monta el anuncio
completo de verdad (text cards, slideshow, fuentes, música, concatenación). Sirve
para validar el flujo y el diseño de los YAML sin gastar GPU.

## Config YAML
Ver `configs/marli_v2.yaml`. Campos principales:
- raíz: `name`, `fps`, `style`, `camera`, `seed`, `music`, `audio_mix.music_vol`,
  `brand` (`signature`, `accent_color`, `fonts.headline`, `fonts.body`).
- `beats[]`: `n`, `type`, `id`, `dur`, `prompt`, y según el tipo:
  - textcard: `kicker`, `headline`, `subhead`, `cta_pill`, `cta`.
  - slideshow5: `slide_dur`, `slides[]` (prompts), `texts[]` (lower-thirds).
  - ugc: `audio` (`source: tts|recorded|none`, `voice_id`, `text`).

## Coste (orientativo)
Con A40 (48 GB) ~$0.80/h: take completo (6 beats) ≈ 15-20 min de pod + ~2 min de
montaje ≈ **$0.25-0.40 por take**. Iterar 10 takes ≈ $3-4.

## Notas de esta entrega
- Las **fuentes de marca** (DM Serif Display + Space Grotesk) están incluidas (de
  Google Fonts, OFL).
- `music.wav` es un **marcador de posición** sintetizado; sustitúyelo por tu pista
  real (mismo nombre) — track épico con trompetas/tambores.
- Los 4 workflows son **plantillas válidas en formato API**: funcionan como punto
  de partida y son parcheables, pero exporta los tuyos reales desde ComfyUI para
  control fino de calidad.
- El `sting` de tambor por cambio de slide y el lip-sync de UGC quedan como
  enganches preparados (ver YAML y `ugc_wan22.json`).
