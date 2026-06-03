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

## 2. Storytelling (S1)
- **R2.1** Arco claro por pieza (p.ej. hook → dolor → solución → revelación → oferta → marca).
- **R2.2** Cada segmento declara su **rol** (en `concepto`/comentario), su `formato`,
  lo que **dice** (`voz_off` o `avatar.dialogo`) y su `texto_pantalla`.
- **R2.3** Hooks que se leen en <2 s. Copys del arsenal de marca.
- **R2.4** Persona objetivo por defecto: la psicóloga saturada (la que mejor convierte).
- **R2.5** Prompts limpios: sin marcas reales, sin famosos, sin texto incrustado largo
  (gpt-image escribe texto ilegible → el texto va en post, no en la imagen).

## 3. Identidad visual
- **R3.1** Estilo de marca en TODOS los prompts vía `{ESTILO}` (render 3D limpio,
  luz suave, rojo `#E24B4A`, crema `#FAF6F1`, sin neón/cyberpunk).
- **R3.2** Tipografía **Inter**; palabra clave en **rojo Marli**; lower-third con barra de acento.
- **R3.3** Robot **Li** presente cuando aplique. Cada pieza termina con `cierre_marca`.
- **R3.4** Slideshow: tarjeta de valor (`texto`) por still.

## 4. Formatos
- **R4.1** Respetar `FORMATOS.md` (motor, audio, campos obligatorios por formato).
- **R4.2** Duración por clip WAN ≈ 5 s (81 frames @16fps). Más → encadenar segmentos.
- **R4.3** Aspecto y resolución de salida fijos por paquete (`salida`).

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
