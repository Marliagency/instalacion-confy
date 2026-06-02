# Sesión A — Guionista / Arquitecto (SIN GPU)

Objetivo: convertir un brief + recursos de empresa en un **paquete de producción
validado** (`production_package.json`) que la Sesión B ejecuta sin pensar.
No enciende ningún pod. Coste ≈ 0.

## Entradas
- Brief del usuario / objetivo del anuncio.
- Info de empresa (p.ej. el doc maestro de Marli en **Notion**).
- (Fase 2) Imágenes/recursos de producto en `assets/product/`.

## Pasos
1. Lee la marca: paleta, tipografía (Inter), estilo visual, personaje (Li),
   buyer persona, hooks y copys del documento maestro.
2. Define el **concepto** y los **hooks** de storytelling (dolor → solución →
   transformación → promesa de marca).
3. Escribe los **segmentos** eligiendo formato por escena (ver tabla). Por cada
   segmento: prompt de imagen (usa `{ESTILO}` para inyectar el estilo de marca),
   prompt de movimiento/cámara, `texto_pantalla`, `voz_off` y/o `avatar.dialogo`,
   `duracion_s`/`frames`, `seed`.
4. Rellena marca / salida / generación (modelo de imagen = `gpt-image-1` calidad
   `medium`; voz = `elevenlabs` con `voz_id`).
5. **Valida**: `python3 pipeline.py production_package.json` (debe decir
   "Validación estricta: sí" y listar imágenes + segmentos).
6. Commit del paquete. Avisa a la Sesión B.

## Tabla de formatos (qué motor usa cada uno)
| `formato`   | Úsalo para…                          | Motor (Sesión B)       | GPU |
|-------------|--------------------------------------|------------------------|-----|
| `cinematic` | plano peli, cámara lenta, DoF        | `wan_i2v`              | sí  |
| `pov_phone` | POV/selfie handheld, look de móvil   | `wan_i2v`              | sí  |
| `product`   | producto con parallax/rotación       | `wan_i2v`              | sí  |
| `slideshow` | 3-6 stills con Ken Burns             | ffmpeg (local)         | no  |
| `ugc`       | avatar que habla (lip-sync a voz)    | `wan_lipsync`          | sí  |

Reglas: combina formatos para ritmo (un cinematográfico + un UGC testimonial +
un POV de producto + un slideshow de beneficios + cierre de marca). Duración por
clip WAN ≈ 5 s (81 frames @16fps); para más, encadena segmentos.

## Salida (entregable de esta sesión)
- `production_package.json` validado (committeado).
- (Fase 2) recursos de producto referenciados con `imagen.ref_producto`.
