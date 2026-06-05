# STUDIO_PLAN.md — Plataforma de producción multi-empresa ("Estudio")

> Estado: **PLAN para aprobar.** No se construye nada hasta tu OK.
> Decisiones tomadas: (1) **Framework operado por Claude** (no app web); (2) empezar
> por un **plan detallado**, con foco en que la **estructura de montaje y el orden de
> generación de recursos** queden blindados.

---

## 0. Objetivo y principio rector

Estandarizar la producción de vídeo para **varias empresas**, donde cada entrega es un
**vídeo de 30-60s compuesto de varios formatos** (UGC lip-sync + b-roll + slideshow +
cards + insertos de captura…), con la **marca y assets de cada empresa**.

**Principio rector (lo que pediste):** los recursos se generan en un **orden de
dependencias** y existe un **gate de validación** previo al montaje. **Nunca se monta un
vídeo si a algún segmento le falta un asset requerido** (p.ej. un UGC sin su voz → sin
lip-sync). El montaje es la última fase y solo corre sobre un manifiesto 100% completo.

---

## 1. Estructura del repo (multi-proyecto)

```
projects/
  <empresa>/
    brand.json            # kit de marca (paleta, fuentes, voz, estilo, mascota/producto, personajes)
    assets/
      characters/         # retratos persistentes (generados 1 vez, reutilizados)
      refs/               # refs de mascota/producto (R7: se respetan siempre)
      screenshots/        # capturas reales de app/producto (para insertos)
      music/              # pistas reutilizables (o se generan)
    pieces/
      <pieza>.json        # el guion (hereda brand.json): segmentos + formatos + copy + refs
    outputs/              # vídeos montados + assets intermedios
engine/                   # motor compartido (refactor de lo ya hecho)
blueprints/               # plantillas de pieza (composición 30-60s estandarizada)
studio.py                 # ORQUESTADOR único (un comando hace todo)
STUDIO_PLAN.md            # este documento
```

Marca y assets viven **por empresa**; las piezas **heredan** la marca → no se repite el
branding en cada guion. Todo versionado en git (control + historial).

---

## 2. Modelo de datos

**`brand.json`** (por empresa): `nombre`, `paleta`, `fuentes`, `estilo_visual`,
`voz` (motor + voz_id ElevenLabs + ajustes), `musica` (estilo/ruta), `mascota/producto`
(descripción + refs), `personajes` (id → prompt + calidad + retrato), `defaults`
(aspecto, fps, duración objetivo, marco/transiciones).

**`pieces/<pieza>.json`** (hereda brand): lista de `segmentos`. Cada segmento declara:
- `formato` (uno de los 10+),
- `texto_pantalla` (copy en pantalla, SIEMPRE mayúsculas en el render),
- `voz_off` (narración) **o** `avatar.dialogo` (habla del personaje, UGC),
- `imagen`/`imagenes` (+ `referencias` para R7) y/o `captura` (inserto),
- `animacion`, `duracion_s`, `seed`.

**Manifiesto de assets (derivado):** el motor calcula, a partir de la pieza, la lista
EXACTA de assets que cada segmento necesita y en qué fase se generan (sección 3).

---

## 3. ⭐ Dependencias y ORDEN de generación (el núcleo)

### 3.1 Qué necesita cada formato (grafo de dependencias)

| Formato | Assets requeridos (en orden) | Clip resultante |
|---|---|---|
| `ugc`, `ugc_pov` | personaje (retrato) → **voz del diálogo (ElevenLabs)** → clip **lip-sync** (InfiniteTalk) | habla sincronizada real |
| `cinematic`,`pov_phone`,`product`,`screen_demo`,`hands_asmr` | imagen (OpenAI, refs R7) → clip **i2v** (WAN) | b-roll animado |
| `slideshow` | N imágenes (OpenAI) → clip Ken Burns (local) | secuencia |
| `before_after` | 2 imágenes → clip wipe (local) | antes/después |
| `kinetic_text`,`stat_reveal` | (solo texto) | tarjeta tipográfica (local) |
| `screenshot_insert` (estilo QYRO) | clip base (i2v/t2v) **+** captura real del proyecto → composición (local) | clip con inserto de móvil |
| *Narración* (cualquier segmento con `voz_off`) | texto → **voz en off (ElevenLabs)** | audio colocado en el montaje |

> **Regla dura:** si un segmento es `ugc`, su **voz es obligatoria** (sin voz no hay
> lip-sync). Si tiene `voz_off`, esa voz es obligatoria. Si es `screenshot_insert`, la
> captura es obligatoria. El motor lo **exige** (sección 3.3).

### 3.2 Fases del orquestador (orden topológico, NO se saltan)

```
A. Personajes persistentes  (OpenAI high, 1 vez, reutilizados)        [in-pod]
B. Imágenes de segmento      (OpenAI, refs respetadas R7)             [in-pod]
C. VOCES  → diálogos UGC + voces en off  (ElevenLabs)                 [in-pod]   ← lo que faltó en QYRO
D. Música                    (ElevenLabs o reutiliza la del proyecto) [in-pod]
E. Modelos                   (fetch_models según motores presentes)   [in-pod]
F. Clips GPU                 (i2v + lip-sync; el lip-sync CONSUME C)   [pod/ComfyUI]
G. Clips locales             (slideshow, cards, before/after, insertos)[local]
H. ⛔ GATE DE VALIDACIÓN DEL MANIFIESTO  (ver 3.3)                     [local]
I. Montaje                   (assemble: transiciones, marcos, copy, audio con ducking) [local]
J. Entrega + APAGAR/BORRAR pod                                        [API]
```

El orden A→F es lo que evita la rotura: la fase F (lip-sync) **no puede correr** sin la
fase C (voz). El orquestador construye el grafo y respeta dependencias siempre.

### 3.3 ⛔ Gate de validación (la garantía anti-"vídeo roto")

Antes de montar (fase H), el motor recomputa el manifiesto y comprueba, **segmento por
segmento**, que existen TODOS sus assets requeridos:
- `ugc` → existe `clip lip-sync` **y** `voz del avatar`.
- segmento con `voz_off` → existe el `mp3` de esa voz.
- `screenshot_insert` → existe el `clip base` **y** la `captura`.
- i2v/slideshow/etc. → existe el clip correspondiente.

Si algo falta: **o** se autogenera (si es regenerable y tú lo permites) **o** se ABORTA
con un mensaje claro (`Segmento s3 [ugc]: falta voz → no se puede lip-sync`). **Nunca**
se entrega un vídeo con estructura incompleta. `studio.py plan` corre este gate **en
seco** (sin gastar GPU) para que veas la estructura antes de producir.

---

## 4. Blueprints (composición 30-60s estandarizada)

Generadores paramétricos de piezas que **siempre** producen una estructura multi-formato
válida y completa para la duración objetivo. Ejemplos iniciales:
- `ugc_testimonial_30s`: hook UGC (lip-sync) → 2-3 b-roll i2v → slideshow CTA + cierre.
- `app_demo_60s` (estilo QYRO): hook → 3 b-roll con **insertos de captura** → stat/kinetic → manifiesto + cierre.
- `product_launch_45s`: cinematic → product → before/after → UGC CTA + cierre.

Cada blueprint toma los **defaults de la marca**, te deja rellenar copy/refs/capturas, y
**declara las dependencias correctas** (un UGC siempre trae su `dialogo`, etc.), así la
estructura nace bien montada.

---

## 5. `studio.py` (orquestador) — comandos

```
studio.py new-project <slug>                       # scaffold de projects/<slug>/
studio.py new-piece   <slug> --blueprint <name>    # crea pieces/<pieza>.json desde blueprint
studio.py plan        <slug> <pieza>               # DRY-RUN: manifiesto, orden, gate de estructura, COSTE estimado (sin GPU)
studio.py produce     <slug> <pieza> [--yes]       # fases A→J; pide confirmación antes de encender GPU
studio.py status      <slug>                        # qué piezas/outputs hay
```

`produce` encapsula TODO lo que hoy hago a mano (crear pod → gen_inpod → comfy_run →
build_* → assemble → entrega → apagar pod), en el **orden** de la sección 3.

---

## 6. Control y gates de coste

- `plan` muestra: nº de imágenes/voces, nº de clips GPU, tiempo y **coste estimado**, y
  el **check de estructura** (cada segmento con sus dependencias resueltas).
- Confirmación obligatoria **antes de encender GPU** (regla de coste).
- Specs versionados en git → control total y trazabilidad por empresa.

---

## 7. Reutilización (lo ya construido que se recicla)

`pipeline.py`, `formats.py`, `comfy_run.py`, `gen_inpod.py`, `assemble_pkg.py`,
`build_slideshow/cards/before_after.py`, `build_characters.py`, `build_qyro_montage.py`
(→ se generaliza como formato `screenshot_insert`), `tts*.py`, `music_eleven.py`,
`fetch_models.py`, `runpod_ctl.py`, `pod_exec.py`, workflows validados. ≈70% del motor ya
existe; el trabajo es **organizarlo por proyectos + orquestar + blindar el orden**.

---

## 8. Fases de CONSTRUCCIÓN (cuando apruebes este plan)

1. **Esquemas + resolver de dependencias + gate de validación** (`engine/manifest.py`):
   brand.json/piece schema, cálculo del manifiesto, fases A→J, validación H. *(núcleo)*
2. **`studio.py`** orquestador (encadena A→J con gates de coste).
3. **Generalizar `screenshot_insert`** dentro del montaje (lo de QYRO deja de ser script aparte).
4. **2-3 blueprints** de 30-60s.
5. **Migrar `projects/marli` y `projects/qyro`** + smoke test end-to-end de cada uno.
6. **Runbook de operador** (cómo lo lanzo en cada sesión permitida) + actualizar CLAUDE.md.

---

## 9. Riesgos / decisiones abiertas

- **Red/proxy:** la producción debe correr en una sesión Claude con allowlist correcto +
  pods RunPod (no en tu Mac). El framework asume esto.
- **Capturas/refs:** las aportas tú por proyecto (a `assets/`); si faltan, el gate lo
  avisa antes de gastar.
- **Coste:** un pod por producción; se apaga/borra al terminar. `plan` estima antes.
