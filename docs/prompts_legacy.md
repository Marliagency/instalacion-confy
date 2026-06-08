# Prompts manuales (LEGACY) — archivado

> La operación del estudio **ya no se hace pegando prompts a mano**. Todo paso
> mecánico es ahora un subcomando de `studio.py` (o el webhook de n8n), y los dos
> pasos creativos (brief→pieza y copy) se ejecutan dentro de `studio.py` llamando
> a la API de Anthropic (`engine/llm.py`). Ver `README.md`.

## Equivalencias (prompt manual antiguo → comando)

| Antes (prompt a mano)                                  | Ahora (comando)                                  |
|--------------------------------------------------------|--------------------------------------------------|
| A1 — rellenar brand desde info                         | `studio.py init-brand <slug> --info <file>`      |
| B1/B2 — convertir brief en pieza                       | `studio.py brief2piece <slug> <pieza> --brief …` |
| C1/C2/C3 — rellenar prompts/diálogos/voz               | `studio.py fill <slug> <pieza>`                  |
| E2 — regenerar un clip                                 | `studio.py regen-segment <slug> <pieza> <seg>`   |
| E3 — variantes de escena de un personaje               | `studio.py add-scene <slug> <char> --scenes …`   |
| E4 — fotograma final (FLF)                             | `studio.py flf-end <slug> <pieza> <seg> --change`|
| Todo el flujo de un vídeo                              | `studio.py make <slug> --brief "<idea>"`         |

La organización conceptual S1 (guionista) / S2 (productor) / S3 (montaje) sigue
siendo válida como modelo mental (ver `SESION_1/2/3.md`), pero su ejecución ya no
requiere intervención humana salvo el `--brief` y aportar assets de usuario.
