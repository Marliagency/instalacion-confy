#!/usr/bin/env python3
"""
pipeline.py — Núcleo compartido del paquete de producción (Fase 2).

Lo usan tanto la generación de imágenes (Sesión B, in-pod) como el runner de
ComfyUI y el montaje final. Carga/valida el paquete, resuelve el motor de cada
formato, inyecta el estilo de marca en los prompts y "aplana" el paquete en:
  - items de imagen a generar con OpenAI (uno por segmento, o N para slideshow),
  - segmentos resueltos (con su motor) para generar el clip correspondiente.

Formato -> motor:
    cinematic | pov_phone | product  -> wan_i2v       (ComfyUI, image-to-video)
    ugc                              -> wan_lipsync   (ComfyUI, lip-sync a audio)
    slideshow                        -> slideshow_ffmpeg (local, sin GPU)
"""
import json
import os

ENGINE_BY_FORMAT = {
    # vídeo generativo (WAN i2v) — mismo motor, cambia el prompt/cámara
    "cinematic": "wan_i2v",
    "pov_phone": "wan_i2v",
    "product":   "wan_i2v",
    "screen_demo": "wan_i2v",   # pantalla/UI del producto en acción
    "hands_asmr":  "wan_i2v",   # manos interactuando, estética ASMR
    # avatar hablando (lip-sync a audio)
    "ugc":       "wan_lipsync",
    # composiciones locales (ffmpeg, sin GPU)
    "slideshow":    "slideshow_ffmpeg",
    "kinetic_text": "ffmpeg_card",   # tipografía animada (hook/CTA)
    "stat_reveal":  "ffmpeg_card",   # número grande animado
    "before_after": "ffmpeg_ba",     # antes (caos) → después (calma)
}

# Tamaño de imagen OpenAI más cercano al aspecto de salida
ASPECT_TO_SIZE = {
    "9:16": "1024x1536", "4:5": "1024x1536",
    "1:1": "1024x1024",
    "16:9": "1536x1024",
}


def load_package(path):
    with open(path, "r", encoding="utf-8") as f:
        pkg = json.load(f)
    _basic_check(pkg)
    return pkg


def _basic_check(pkg):
    for k in ("marca", "salida", "generacion", "piezas"):
        if k not in pkg:
            raise ValueError(f"Falta la clave de nivel superior '{k}' en el paquete.")
    if not pkg["piezas"]:
        raise ValueError("El paquete no tiene piezas.")
    for pieza in pkg["piezas"]:
        for seg in pieza["segmentos"]:
            if seg.get("formato") not in ENGINE_BY_FORMAT:
                raise ValueError(f"Segmento {seg.get('id')}: formato inválido '{seg.get('formato')}'.")


def validate_schema(pkg, schema_path="schema/production_package.schema.json"):
    """Validación estricta opcional (requiere jsonschema)."""
    try:
        import jsonschema
    except ImportError:
        return None  # validación estricta no disponible; _basic_check ya pasó
    schema = json.load(open(schema_path))
    jsonschema.validate(pkg, schema)
    return True


def style(pkg):
    return pkg.get("marca", {}).get("estilo_visual", "")


def inject_style(prompt, pkg):
    """Sustituye el marcador {ESTILO} por el estilo de marca (o lo antepone)."""
    est = style(pkg)
    if "{ESTILO}" in (prompt or ""):
        return prompt.replace("{ESTILO}", est)
    return f"{est}. {prompt}" if est else prompt


def _refs(im):
    """Rutas de referencia de un nodo imagen (referencias[] o ref_producto)."""
    refs = list(im.get("referencias") or [])
    rp = im.get("ref_producto")
    if rp and rp not in refs:
        refs.append(rp)
    return refs


def character_retrato(pkg, cid):
    """Ruta del retrato de un personaje (definida o por defecto assets/characters/<id>.png)."""
    for c in pkg.get("personajes", []):
        if c["id"] == cid:
            return c.get("retrato") or f"assets/characters/{cid}.png"
    return f"assets/characters/{cid}.png"


def iter_characters(pkg):
    """Personajes persistentes a generar UNA vez (gpt-image-1, calidad alta por defecto)."""
    for c in pkg.get("personajes", []):
        yield {
            "id": c["id"],
            "prompt": inject_style(c.get("prompt", ""), pkg),
            "negativo": c.get("negativo", ""),
            "calidad": c.get("calidad", "high"),
            "retrato": c.get("retrato") or f"assets/characters/{c['id']}.png",
        }


def image_size(pkg):
    gen = pkg.get("generacion", {}).get("imagenes", {})
    if gen.get("tamano"):
        return gen["tamano"]
    return ASPECT_TO_SIZE.get(pkg["salida"].get("aspecto", "9:16"), "1024x1536")


def iter_image_items(pkg):
    """Aplana el paquete en items de imagen a generar con OpenAI.

    Devuelve dicts: {id, prompt, negativo, size, uid, pieza_id, seg_id, formato, idx}
    `uid` = <pieza_id>__<seg_id> (único entre piezas); `id` = nombre de archivo PNG
    (uid, o uid_<n> para slideshow). Así un paquete con N piezas no colisiona.
    """
    size = image_size(pkg)
    for pieza in pkg["piezas"]:
        pid = pieza["id"]
        for seg in pieza["segmentos"]:
            uid = f"{pid}__{seg['id']}"
            fmt = seg["formato"]
            if fmt in ("slideshow", "before_after"):   # varias imágenes desde imagenes[]
                for i, im in enumerate(seg.get("imagenes", []), 1):
                    yield {
                        "id": f"{uid}_{i}",
                        "prompt": inject_style(im.get("prompt", ""), pkg),
                        "negativo": im.get("negativo", ""),
                        "referencias": _refs(im),
                        "size": size, "uid": uid, "pieza_id": pid,
                        "seg_id": seg["id"], "formato": fmt, "idx": i,
                    }
            elif fmt in ("kinetic_text", "stat_reveal") or seg.get("personaje"):
                # texto puro (sin imagen) o usa el retrato del personaje -> no generar imagen
                continue
            else:
                im = seg.get("imagen", {})
                yield {
                    "id": uid,
                    "prompt": inject_style(im.get("prompt", ""), pkg),
                    "negativo": im.get("negativo", ""),
                    "referencias": _refs(im),
                    "size": size, "uid": uid, "pieza_id": pid,
                    "seg_id": seg["id"], "formato": fmt, "idx": 0,
                }


def iter_segments(pkg):
    """Devuelve cada segmento resuelto con su motor, uid y la pieza a la que pertenece."""
    order = 0
    for pieza in pkg["piezas"]:
        seg_order = 0
        for seg in pieza["segmentos"]:
            order += 1; seg_order += 1
            uid = f"{pieza['id']}__{seg['id']}"
            personaje = seg.get("personaje")
            yield {
                "order": order,
                "seg_order": seg_order,
                "id": seg["id"],
                "uid": uid,
                "formato": seg["formato"],
                "engine": ENGINE_BY_FORMAT[seg["formato"]],
                "seg": seg,
                "pieza_id": pieza["id"],
                "personaje": personaje,
                # imagen base: retrato del personaje (reutilizado) o la del propio segmento
                "start_image": f"{personaje}.png" if personaje else f"{uid}.png",
            }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Inspecciona/valida un paquete de producción.")
    ap.add_argument("package")
    ap.add_argument("--schema", default="schema/production_package.schema.json")
    args = ap.parse_args()
    pkg = load_package(args.package)
    strict = validate_schema(pkg, args.schema)
    print(f"Paquete OK. Validación estricta: {'sí' if strict else 'no disponible (instala jsonschema)'}")
    imgs = list(iter_image_items(pkg))
    segs = list(iter_segments(pkg))
    print(f"\nImágenes a generar (OpenAI {pkg['generacion']['imagenes'].get('calidad')}): {len(imgs)}")
    for it in imgs:
        print(f"  - {it['id']:16} [{it['formato']:9}] {it['size']}  {it['prompt'][:60]}…")
    print(f"\nSegmentos/clips: {len(segs)}")
    for s in segs:
        seg = s["seg"]
        extra = seg.get("texto_pantalla") or (seg.get("avatar", {}) or {}).get("dialogo") or ""
        print(f"  {s['order']}. {s['id']:14} [{s['formato']:9} -> {s['engine']:16}] {seg.get('duracion_s')}s  {extra[:45]}")
