# Registro de formatos de vídeo (canónico)

Cada segmento de una pieza declara un `formato`. Esta tabla es la **fuente de verdad**:
define el motor, si usa GPU, qué campos necesita, y **cómo se comporta el audio**.
La S1 (guionista) elige el formato por escena; la S2 lo genera; la S3 lo respeta.

| `formato` | Motor | GPU | Campos obligatorios | Audio | Duración | Cuándo usarlo |
|---|---|---|---|---|---|---|
| `cinematic` | `wan_i2v` | sí | `imagen.prompt`, `animacion.prompt_movimiento` | voz en off (narrador) + música | ~5 s (81f) | plano peli, emoción, dolor, aspiración |
| `pov_phone` | `wan_i2v` | sí | `imagen.prompt`, `animacion` (handheld) | voz en off + música | ~5 s | demo inmersiva, "enséñame que funciona", selfie/POV |
| `product` | `wan_i2v` | sí | `imagen.prompt`, `animacion` (orbit/parallax) | voz en off + música | ~5 s | héroe de producto, revelar a Li |
| `slideshow` | ffmpeg (local) | **no** | `imagenes[]` (3-6) con `prompt` y `texto` | voz en off + música | ~6-8 s | apilar valor/oferta con tarjetas |
| `ugc` | `wan_lipsync` (i2v como fallback) | sí | `imagen.prompt` (retrato), `avatar.dialogo` | **voz del avatar (lip-sync); SIN voz en off; música SILENCIADA** | ~5-6 s | testimonio con cara, hook humano |

## Reglas de audio por formato (resumen)
- **UGC**: el clip lleva **la voz del avatar** sincronizada. → **NUNCA** voz en off encima, y la **música se silencia** durante ese segmento (ya forzado en `assemble_pkg.py`). El UGC se respeta "en crudo".
- **cinematic / pov_phone / product / slideshow**: clip **mudo** → se le pone **voz en off** (narrador) y **música** de fondo (baja).

## Notas técnicas
- `wan_i2v` cubre cinematic/pov/product: **el mismo workflow**, cambia el prompt/cámara.
- `slideshow` no consume GPU (Ken Burns + tarjetas de valor con ffmpeg).
- `ugc` necesita el setup de lip-sync (InfiniteTalk/MultiTalk; ver `workflows/api/wan_lipsync.json`).
  Hasta validarlo, cae a `wan_i2v` (retrato animado) con la voz del avatar encima.
- Resolución de generación WAN por aspecto en `formats.py` (9:16 → 480×832).
- Mapeo `formato → motor` en `pipeline.py` (`ENGINE_BY_FORMAT`).
