# SESIÓN 1 — GUIONISTA (sin GPU, $0)

Escribe el **guion + los prompts** en un único `production_package.json`. Aquí vive
todo el storytelling y el control creativo del usuario. No enciende nada.

## PROMPT DE ARRANQUE (pégalo para empezar)
```
Eres el GUIONISTA (Sesión 1) del pipeline Marli. Lee CLAUDE.md, REGLAS.md,
FORMATOS.md y schema/production_package.schema.json.

Brief: «<aquí tu idea / objetivo / nº de piezas / producto a destacar>».
Recursos: <fotos de producto en assets/product/, datos, doc de marca en Notion>.

Escribe production_package.json con todas las piezas siguiendo la ESPINA DE
RETENCIÓN VIRAL (R2): hook 0-2 s + factor inesperado/pattern-interrupt obligatorio
(campo `gancho`) + open loop + ritmo sin aire muerto + re-hook a mitad + payoff + CTA.
Por cada segmento: formato (FORMATOS.md), prompt de imagen ULTRADETALLADO (R2b:
sujeto+acción+entorno+óptica+iluminación+materiales+paleta+estilo, con {ESTILO}),
prompt de movimiento/cámara, texto en pantalla, voz (voz_off o avatar.dialogo según
formato), duración y seed. Si aporto imágenes de referencia (mascota/producto),
ponlas en `imagen.referencias` — se PRESERVAN sin cambiar diseño ni forma (R7).
Respeta TODAS las reglas (R1: nada de voz/música sobre UGC). Antes de cerrar,
muéstrame los copys, el `gancho` y el arco de cada pieza en una tabla para aprobar/
ajustar. Valida con `python3 pipeline.py production_package.json`. Commit con mi OK.
```

## Entradas
- Brief del usuario (idea, nº de piezas/variaciones, producto, objetivo).
- Doc de marca (Notion), arsenal de copys, persona objetivo.
- (Opcional) recursos del usuario: fotos de producto (`imagen.ref_producto`), música.

## Salida
- `production_package.json` validado y **aprobado por el usuario** (commit).

## Pasos
1. Lee marca, `REGLAS.md`, `FORMATOS.md`, el schema.
2. Define concepto y arco por pieza (R2.1).
3. Escribe cada segmento eligiendo formato (FORMATOS.md) y respetando el audio por
   formato (R1): UGC → `avatar.dialogo` (sin voz_off); resto → `voz_off`.
4. Usa `{ESTILO}` en todos los prompts de imagen (R3.1). Texto en pantalla por escena.
5. (Opcional) marca `variaciones: N` en segmentos donde quieras varias tomas (R5.1).
6. **Muestra al usuario** los copys + arco (tabla) y espera su OK / cambios.
7. `python3 pipeline.py production_package.json` (valida schema + lista imágenes/segmentos).
8. Commit. Avisa a la Sesión 2.

## El usuario manda aquí
El paquete es el guion: el usuario puede reescribir copys, reordenar, cambiar
formatos, duraciones, añadir/quitar escenas o sus propios assets. Nada se genera
hasta que aprueba.
