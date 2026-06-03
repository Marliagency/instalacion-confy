# SESIÓN 3 — EDITOR (sin GPU, $0)

Revisa el banco de assets (control de calidad), **selecciona** las mejores tomas,
descarta/marca las malas y **monta los vídeos coherentes**. Sin GPU → re-edita gratis
las veces que haga falta.

## PROMPT DE ARRANQUE
```
Eres el EDITOR (Sesión 3) del pipeline Marli. Lee REGLAS.md y FORMATOS.md.
Tengo el banco de assets (outputs/) + outputs/manifest.json + production_package.json.

1) REVISA: genera contact sheets (review.py) y mira un fotograma de cada clip e
   imagen. Verifica que cada toma cumple su hueco del guion (qué dice / qué muestra).
   Descarta caras deformadas, texto ilegible, off-brand o movimiento roto.
2) SELECCIONA: si hay variaciones, elige la mejor por hueco → seleccion.json. Marca
   las que haya que regenerar (vuelven a S2).
3) MONTA respetando TODAS las reglas (sobre todo R1: NADA de voz en off ni música
   sobre los UGC; música mute bajo UGC). Un MP4 por pieza:
   `assemble_pkg.py --package … --out-dir outputs`.
4) Enséñame el resultado; aplico tus cambios de orden/ritmo/texto y re-render (gratis).
```

## Entradas
- `outputs/` (imágenes, clips, voces) + `outputs/manifest.json` + `production_package.json`.

## Salida
- `outputs/<pieza_id>.mp4` por pieza (entregar con SendUserFile) + `seleccion.json`
  (qué tomas se usaron, cuáles rechazadas).

## Pasos
1. **Revisar (QC)**: contact sheets de todos los assets; revisar fotograma + (si hace
   falta) verificar que el audio coincide con el guion (R5.2). El significado lo da el
   guion; aquí solo se confirma que cada toma lo cumple (R5.3).
2. **Seleccionar**: elegir la mejor variación por hueco; marcar rechazos/regeneraciones.
3. **Montar**: `assemble_pkg.py` (respeta R1 audio por formato, branding, cierre).
4. **Iterar con el usuario**: cambios de orden, tiempos, textos, música → re-render sin GPU.

## Por qué la coherencia se mantiene
El guion (S1) define rol + lo que dice + texto de cada segmento, y la voz se generó
de esas líneas. El editor no "adivina" significado: **monta en el orden del guion y
verifica que cada toma cumple su hueco**. No rescata un guion malo (eso es de S1) ni
da realismo perfecto a un clip de IA.

## Control del usuario
La selección y el montaje son archivos editables; el usuario decide qué tomas entran,
el orden, el ritmo y los textos, y se re-renderiza gratis hasta que quede.
