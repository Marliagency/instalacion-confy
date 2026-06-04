# Reglas de producción y edición (obligatorias)

Las leen las 3 sesiones. Son innegociables salvo que el usuario diga lo contrario.

## 1. Audio (lo más importante)
- **R1.1 — No audio encima del UGC.** Un segmento `ugc` lleva la voz del avatar
  (lip-sync). **Prohibido** añadirle voz en off, y la **música se silencia** durante
  ese segmento. (Forzado en `assemble_pkg.py` con `ugc_windows`.)
- **R1.2 — Propiedad del audio:** `voz_off` SOLO en formatos no-UGC; `avatar.dialogo`
  SOLO en UGC. Nunca los dos en el mismo segmento.
- **R1.3 — Música:** colchón bajo (vol 0.5 interno), fade in/out, **mute bajo UGC**.
- **R1.4 — Voz en off por escena**, no continua: cada línea cabe en su clip (corta).
  Total de voz < duración del vídeo (deja silencios con música = más premium).

## 2. Storytelling viral y retención (S1) — "lo mejor"
Objetivo: **máxima retención** en redes (TikTok/Reels/Shorts). Cada pieza sigue la
**espina de retención**:
- **R2.1 — Hook 0-2 s (frenar el scroll):** abre con lo más fuerte (afirmación
  audaz, pregunta, o imagen impactante). El primer fotograma + la primera frase
  deciden todo. Nada de intros lentas.
- **R2.2 — Factor inesperado / pattern interrupt (OBLIGATORIO):** en los primeros
  ~3 s, algo que rompe la expectativa (un giro visual, una frase contraintuitiva,
  un cambio brusco de formato). Es lo que retiene. Cada pieza DEBE tener uno,
  declarado en el segmento (campo `gancho`/comentario).
- **R2.3 — Open loop (curiosidad):** plantea una tensión/pregunta al principio que
  solo se resuelve al final ("lo que pasó después me sorprendió…"). Mantiene viendo.
- **R2.4 — Ritmo sin aire muerto:** corte/cambio cada ~1.5-3 s, movimiento constante,
  variedad de formato (UGC↔cinematográfico↔POV) como recurso de retención.
- **R2.5 — Re-hook a mitad:** un segundo pico (dato sorprendente, giro) hacia la
  mitad para recuperar a quien se cae.
- **R2.6 — Subtítulos SIEMPRE:** se ve en silencio (autoplay muteado). Texto en
  pantalla en cada beat (R3.2).
- **R2.7 — Escalada de valor → payoff → CTA:** cada beat sube la apuesta; cierra
  resolviendo el loop + llamada a la acción clara.
- **R2.8 — Arco y rol por segmento:** cada segmento declara su `formato`, su rol en
  la espina (hook / interrupt / loop / valor / payoff / CTA), lo que **dice**
  (`voz_off` o `avatar.dialogo`) y su `texto_pantalla`.
- **R2.9 — Persona objetivo** por defecto: la psicóloga saturada. Copys del arsenal
  de marca. Sin marcas reales ni famosos.

## 2-bis. Prompts ultradetallados (calidad máxima)
- **R2b.1** Cada prompt de imagen es **exhaustivo**: sujeto + acción + entorno +
  composición/encuadre + **óptica** (focal, profundidad de campo) + **iluminación**
  (dirección, calidad, hora) + materiales/texturas + paleta + estilo + estado de
  ánimo. Nunca prompts vagos.
- **R2b.2** Siempre incluir `{ESTILO}` (marca) + `negativo` específico (qué evitar).
- **R2b.3** El texto legible NO se incrusta en la imagen (gpt-image lo escribe mal);
  va en post (lower-third / tarjetas).

## 3. Identidad visual
- **R3.1** Estilo de marca en TODOS los prompts vía `{ESTILO}` (render 3D limpio,
  luz suave, rojo `#E24B4A`, crema `#FAF6F1`, sin neón/cyberpunk).
- **R3.2** Tipografía **Inter**; palabra clave en **rojo Marli**; lower-third con barra de acento.
- **R3.2b — TODO el texto en pantalla va SIEMPRE en MAYÚSCULAS** (más impacto, mejor
  lectura en silencio). Forzado en código: `assemble_final.caption_clip`, las tarjetas
  de slideshow y los builders ffmpeg ponen `.upper()` aunque el guion venga en minúsculas.
  Excepción: el **wordmark `marli`** (es el logo, se mantiene en minúsculas).
- **R3.3** Robot **Li** presente cuando aplique. Cada pieza termina con `cierre_marca`.
- **R3.4** Slideshow: tarjeta de valor (`texto`) por still.

## 4. Formatos y duración
- **R4.1** Respetar `FORMATOS.md` (motor, audio, campos obligatorios por formato).
- **R4.2** Duración por clip WAN ≈ 5 s (81 frames @16fps). Más → encadenar segmentos.
- **R4.3** Aspecto y resolución de salida fijos por paquete (`salida`).
- **R4.4 — Duración objetivo del vídeo final: ~30 s** (`salida.duracion_objetivo_s: 30`),
  es decir **~6 segmentos** de ~5 s + tarjeta de cierre. El editor (S3) monta ~6 clips
  por vídeo combinando formatos para retención. Excepción: los UGC-largo orgánicos
  pueden ser un único clip de ~20-30 s + B-roll de relleno hasta 30 s.

## 5. Sobre-generación y selección (calidad)
- **R5.1** La S2 puede generar **N variaciones** por segmento (`variaciones`, seeds distintas)
  para que la S3 elija la mejor toma.
- **R5.2** La S3 hace **control de calidad**: revisa un fotograma de cada toma (y verifica
  que el audio coincide con el guion), **descarta** caras deformadas, texto ilegible,
  off-brand o movimiento roto, y marca para regenerar.
- **R5.3** La coherencia la garantiza el **guion** (S1) + la voz/texto atados a cada
  segmento. La S3 NO inventa coherencia; asegura que cada toma cumple su hueco.

## 6. Coste (RunPod)
- **R6.1** Un solo pod por lote (no recrear por vídeo). Apagar/**borrar** al terminar.
- **R6.2** **Descargar imágenes/clips/voces a local EN CUANTO se generan** (un pod sin
  saldo se borra a mitad — pasó el 2026-06-03 con $0.19 de saldo).
- **R6.3** Imagen `medium` + 4 pasos lightx2v = mínimo coste con buena calidad.
- **R6.4** Verificar saldo RunPod (`myself.clientBalance`) y modelos (`comfy_doctor.py`)
  ANTES de gastar.

## 7. Fidelidad de referencias (mascota / producto) — INALTERABLES
Si el usuario aporta imágenes de referencia (la mascota Li, un producto), **se
respetan SIEMPRE: no se cambian ni en diseño ni en forma**. Mecanismo (no es
"pedirlo" al prompt, es forzarlo técnicamente):
- **R7.1** Las referencias se declaran en el segmento: `imagen.referencias: ["assets/product/li.png", …]`
  (o `imagen.ref_producto`). La S1 las asigna a cada segmento que muestre ese elemento.
- **R7.2 — Imagen:** `openai_images.py` genera con la **API de edición** de gpt-image-1
  pasando esas referencias como entrada (image-to-image), de modo que el elemento se
  **preserva** en lugar de re-inventarse. El prompt solo cambia entorno/escena, no el sujeto.
- **R7.3 — Vídeo:** la imagen base (ya fiel a la referencia) es el `start_image` del
  WAN i2v → el movimiento NO altera el diseño. Para lip-sync, el retrato de referencia
  es el `start_image`.
- **R7.4** El `negativo` incluye "altered logo/product, redesigned, different shape/color"
  para reforzar. La S3 (QC) **rechaza** cualquier toma donde la mascota/producto cambie
  de diseño o forma.
- **R7.5** Resolución de la referencia: usar la de mayor calidad disponible; mantener
  proporciones del elemento.

## 8. Personajes persistentes y UGC de máxima calidad
- **R8.1 — Personaje único, generado una vez:** el avatar se define en `personajes[]`
  y se genera **una sola vez** con el **mejor modelo** (`gpt-image-1` calidad **`high`**)
  → `assets/characters/<id>.png`. Si el retrato existe, se **reutiliza** (no se regenera):
  el personaje es **idéntico en todos los vídeos** y se ahorra en imágenes.
- **R8.2 — Reutilización:** los segmentos `ugc` referencian `personaje: "<id>"`; ese
  retrato es el `start_image` del lip-sync. No se generan imágenes por segmento UGC.
- **R8.3 — Vídeo (lip-sync) lo mejor:** motor `wan_lipsync` = **InfiniteTalk** (o MultiTalk)
  a la **máxima resolución viable** (720p+), 4-pasos solo si no degrada la boca.
- **R8.4 — Voz lo mejor:** **ElevenLabs** (`eleven_multilingual_v2`), voz premium en
  español (`voz_id`); el audio conduce el lip-sync (audio-first).
- **R8.5 — Coherencia:** misma cara, misma iluminación y encuadre selfie en todos los
  UGC. La S3 rechaza tomas donde el personaje cambie de rasgos.
