#!/usr/bin/env python3
"""
studio.py — Orquestador del Estudio de producción multi-empresa.

Cada empresa es un proyecto en projects/<slug>/ con su brand.json (marca + assets +
info) y sus pieces/<pieza>.json (guion). Una pieza compone VARIOS formatos en un
vídeo de 30-60s. studio compone brand+pieza en el "paquete" que ya entiende el motor
(pipeline/comfy_run/assemble_pkg), calcula el MANIFIESTO de assets con su ORDEN de
dependencias, y pasa un GATE de validación que impide montar un vídeo con estructura
incompleta (p.ej. un UGC sin voz → sin lip-sync).

Comandos:
    studio.py new-project <slug>
    studio.py new-piece   <slug> <pieza> [--blueprint <name>]
    studio.py plan        <slug> <pieza>          # dry-run: manifiesto + gate + coste (sin GPU)
    studio.py status      <slug>
    studio.py produce     <slug> <pieza> [--yes]  # ejecuta fases A→J (requiere pod/GPU)

Ver STUDIO_PLAN.md para el diseño completo.
"""
import argparse, json, os, sys, glob

PROJECTS = "projects"

# ---------------------------------------------------------------------------
# Modelo de formatos: motor + dependencias + fase de generación
#   needs: clases de asset que el segmento REQUIERE (en orden de dependencia)
#   phase: fase del orquestador donde se produce el CLIP de este segmento
# ---------------------------------------------------------------------------
FORMAT_DEPS = {
    "ugc":          {"engine": "wan_lipsync",       "needs": ["character", "voice_dialogo"], "phase": "F"},
    "ugc_pov":      {"engine": "wan_lipsync",       "needs": ["character", "voice_dialogo"], "phase": "F"},
    "cinematic":    {"engine": "wan_i2v",           "needs": ["image"],   "phase": "F"},
    "pov_phone":    {"engine": "wan_i2v",           "needs": ["image"],   "phase": "F"},
    "product":      {"engine": "wan_i2v",           "needs": ["image"],   "phase": "F"},
    "screen_demo":  {"engine": "wan_i2v",           "needs": ["image"],   "phase": "F"},
    "hands_asmr":   {"engine": "wan_i2v",           "needs": ["image"],   "phase": "F"},
    "t2v":          {"engine": "wan_t2v",           "needs": [],          "phase": "F"},
    "slideshow":    {"engine": "slideshow_ffmpeg",  "needs": ["images"],  "phase": "G"},
    "before_after": {"engine": "ffmpeg_ba",         "needs": ["images2"], "phase": "G"},
    "kinetic_text": {"engine": "ffmpeg_card",       "needs": [],          "phase": "G"},
    "stat_reveal":  {"engine": "ffmpeg_card",       "needs": [],          "phase": "G"},
    "screenshot_insert": {"engine": "composite",    "needs": ["base_clip", "screenshot"], "phase": "G"},
}

# Coste/tiempo aproximado por clip (min de GPU) y de imagen (sólo informativo)
GPU_MIN = {"wan_lipsync": 3.0, "wan_i2v": 1.5, "wan_t2v": 2.0, "composite": 0.0,
           "slideshow_ffmpeg": 0.0, "ffmpeg_card": 0.0, "ffmpeg_ba": 0.0}
GPU_USD_H = 3.29   # H100; el plan avisa


# ---------------------------------------------------------------------------
# Carga y composición brand + pieza -> paquete del motor
# ---------------------------------------------------------------------------
def proj_dir(slug):
    return os.path.join(PROJECTS, slug)


def load_brand(slug):
    p = os.path.join(proj_dir(slug), "brand.json")
    if not os.path.isfile(p):
        sys.exit(f"No existe {p}. Crea el proyecto con: studio.py new-project {slug}")
    return json.load(open(p, encoding="utf-8"))


def load_piece(slug, pieza):
    p = os.path.join(proj_dir(slug), "pieces", f"{pieza}.json")
    if not os.path.isfile(p):
        sys.exit(f"No existe la pieza {p}.")
    return json.load(open(p, encoding="utf-8"))


def compose_package(brand, piece):
    """brand.json + pieza.json -> 'paquete' que entiende pipeline/assemble."""
    return {
        "marca": brand["marca"],
        "salida": brand["salida"],
        "generacion": brand.get("generacion", {"imagenes": {}}),
        "personajes": brand.get("personajes", []),
        "piezas": [piece],
    }


# ---------------------------------------------------------------------------
# Resolución de rutas de assets (con ámbito de proyecto)
# ---------------------------------------------------------------------------
def paths(slug):
    d = proj_dir(slug)
    return {
        "characters": os.path.join(d, "assets", "characters"),
        "screenshots": os.path.join(d, "assets", "screenshots"),
        "refs": os.path.join(d, "assets", "refs"),
        "music": os.path.join(d, "assets", "music"),
        "images": os.path.join(d, "outputs", "images"),
        "voice": os.path.join(d, "outputs", "voice"),
        "clips": os.path.join(d, "outputs", "clips"),
        "out": os.path.join(d, "outputs"),
    }


def segment_manifest(slug, brand, piece):
    """Por cada segmento: motor, fase, assets requeridos (con ruta/exists/origen) e issues."""
    P = paths(slug)
    chars = {c["id"] for c in brand.get("personajes", [])}
    out = []
    for seg in piece["segmentos"]:
        uid = f"{piece['id']}__{seg['id']}"
        fmt = seg.get("formato")
        spec = FORMAT_DEPS.get(fmt)
        m = {"uid": uid, "formato": fmt, "engine": spec["engine"] if spec else "?",
             "phase": spec["phase"] if spec else "?", "assets": [], "issues": []}
        if not spec:
            m["issues"].append(f"formato desconocido '{fmt}'")
            out.append(m); continue

        # --- dependencias declaradas por el formato ---
        for kind in spec["needs"]:
            if kind == "character":
                cid = seg.get("personaje")
                if not cid:
                    m["issues"].append("UGC sin 'personaje' → no hay retrato para lip-sync")
                elif cid not in chars:
                    m["issues"].append(f"personaje '{cid}' no definido en brand.personajes")
                path = os.path.join(P["characters"], f"{cid}.png") if cid else None
                m["assets"].append({"kind": "character", "path": path,
                                    "origen": "generado_o_reutilizado", "exists": bool(path and os.path.isfile(path))})
            elif kind == "voice_dialogo":
                dlg = (seg.get("avatar") or {}).get("dialogo", "").strip()
                if not dlg:
                    m["issues"].append("UGC sin 'avatar.dialogo' → no se puede generar voz → SIN lip-sync")
                m["assets"].append({"kind": "voice_dialogo", "path": os.path.join(P["voice"], f"{uid}.mp3"),
                                    "origen": "generado", "exists": os.path.isfile(os.path.join(P["voice"], f"{uid}.mp3"))})
            elif kind == "image":
                m["assets"].append({"kind": "image", "path": os.path.join(P["images"], f"{uid}.png"),
                                    "origen": "generado", "exists": os.path.isfile(os.path.join(P["images"], f"{uid}.png"))})
            elif kind == "images":
                ims = seg.get("imagenes", [])
                if len(ims) < 2:
                    m["issues"].append("slideshow necesita >=2 imágenes en 'imagenes'")
                for i in range(1, len(ims) + 1):
                    pth = os.path.join(P["images"], f"{uid}_{i}.png")
                    m["assets"].append({"kind": "image", "path": pth, "origen": "generado", "exists": os.path.isfile(pth)})
            elif kind == "images2":
                ims = seg.get("imagenes", [])
                if len(ims) < 2:
                    m["issues"].append("before_after necesita 2 imágenes en 'imagenes'")
                for i in range(1, max(2, len(ims)) + 1):
                    pth = os.path.join(P["images"], f"{uid}_{i}.png")
                    m["assets"].append({"kind": "image", "path": pth, "origen": "generado", "exists": os.path.isfile(pth)})
            elif kind == "base_clip":
                m["assets"].append({"kind": "base_clip", "path": os.path.join(P["clips"], f"{uid}.mp4"),
                                    "origen": "generado", "exists": os.path.isfile(os.path.join(P["clips"], f"{uid}.mp4"))})
            elif kind == "screenshot":
                cap = seg.get("captura")
                if not cap:
                    m["issues"].append("screenshot_insert sin 'captura'")
                pth = os.path.join(P["screenshots"], cap) if cap else None
                ex = bool(pth and os.path.isfile(pth))
                if cap and not ex:
                    m["issues"].append(f"falta la captura assets/screenshots/{cap} (apórtala tú)")
                m["assets"].append({"kind": "screenshot", "path": pth, "origen": "usuario", "exists": ex})

        # --- voz en off (cualquier segmento narrado) ---
        if seg.get("voz_off"):
            pth = os.path.join(P["voice"], f"{uid}_vo.mp3")
            m["assets"].append({"kind": "voice_off", "path": pth, "origen": "generado", "exists": os.path.isfile(pth)})

        # --- captura como inserto en formatos que no son screenshot_insert (p.ej. t2v/i2v) ---
        cap = seg.get("captura")
        if cap and "screenshot" not in spec["needs"]:
            pth = os.path.join(P["screenshots"], cap)
            ex = os.path.isfile(pth)
            if not ex:
                m["issues"].append(f"falta la captura assets/screenshots/{cap} (apórtala tú)")
            m["assets"].append({"kind": "screenshot_overlay", "path": pth, "origen": "usuario", "exists": ex})

        # --- refs de imagen (R7): deben existir si se citan ---
        im = seg.get("imagen") or {}
        for r in (im.get("referencias") or []):
            rp = r if os.path.isabs(r) else r
            ex = os.path.isfile(rp)
            if not ex:
                m["issues"].append(f"falta la referencia {r} (R7, apórtala tú)")
            m["assets"].append({"kind": "ref", "path": rp, "origen": "usuario", "exists": ex})

        # clip de salida de este segmento
        m["clip"] = os.path.join(P["clips"], f"{uid}.mp4")
        m["clip_exists"] = os.path.isfile(m["clip"])
        out.append(m)
    return out


def music_status(slug, brand):
    ruta = ((brand["salida"].get("musica") or {}).get("ruta")) or ""
    return ruta, (bool(ruta) and os.path.isfile(ruta))


def cost_estimate(mani):
    gpu_min = sum(GPU_MIN.get(m["engine"], 0.0) for m in mani)
    overhead = 8.0  # arranque pod + descarga modelos aprox
    total_min = gpu_min + overhead
    return total_min, total_min / 60.0 * GPU_USD_H


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------
def cmd_plan(args):
    brand = load_brand(args.slug); piece = load_piece(args.slug, args.pieza)
    mani = segment_manifest(args.slug, brand, piece)
    mruta, mok = music_status(args.slug, brand)
    n = len(mani)
    print(f"\n=== PLAN  {args.slug} / {args.pieza}  ({n} segmentos) ===")
    print(f"marca: {brand['marca'].get('nombre')} | voz: {brand['salida']['voz_off'].get('voz_id')} | "
          f"aspecto {brand['salida'].get('aspecto')}")
    # tabla por segmento
    print("\n  #  segmento            formato        motor          fase  requiere")
    user_missing, spec_issues = [], []
    for i, m in enumerate(mani, 1):
        needs = ", ".join(f"{a['kind']}{'' if a['exists'] else '·falta' if a['origen']=='usuario' else '·gen'}"
                          for a in m["assets"]) or "—"
        print(f"  {i:<2} {m['uid']:<18} {m['formato']:<13} {m['engine']:<13} {m['phase']:<4}  {needs}")
        for a in m["assets"]:
            if a["origen"] == "usuario" and not a["exists"]:
                user_missing.append((m["uid"], a["kind"], a["path"]))
        for iss in m["issues"]:
            spec_issues.append((m["uid"], iss))
    # música
    print(f"\n  música: {mruta or '(sin definir)'}  {'OK' if mok else '·se generará/falta'}")
    # coste
    tot_min, usd = cost_estimate(mani)
    gpu_clips = [m for m in mani if GPU_MIN.get(m['engine'], 0) > 0]
    print(f"\n  coste estimado: ~{tot_min:.0f} min de pod (≈{len(gpu_clips)} clips GPU)  →  ~${usd:.2f} (H100)")
    # GATE de estructura (spec)
    print("\n  --- GATE de estructura (anti vídeo roto) ---")
    if spec_issues:
        print("  ⛔ PROBLEMAS DE ESTRUCTURA (corrige el guion antes de producir):")
        for uid, iss in spec_issues:
            print(f"     - {uid}: {iss}")
    else:
        print("  ✅ estructura coherente: cada segmento declara sus dependencias.")
    if user_missing:
        print("\n  ⚠️  ASSETS DE USUARIO QUE FALTAN (apórtalos a projects/%s/assets/):" % args.slug)
        for uid, kind, pth in user_missing:
            print(f"     - {uid}: {kind} → {pth}")
    blockers = len(spec_issues) + len(user_missing)
    print(f"\n  RESULTADO: {'LISTO para produce' if blockers==0 else f'{blockers} bloqueo(s) — resuélvelos primero'}\n")
    return 0 if blockers == 0 else 1


def cmd_status(args):
    brand = load_brand(args.slug)
    print(f"Proyecto {args.slug}: {brand['marca'].get('nombre')}")
    pcs = sorted(glob.glob(os.path.join(proj_dir(args.slug), "pieces", "*.json")))
    print(f"  piezas ({len(pcs)}):")
    for p in pcs:
        name = os.path.splitext(os.path.basename(p))[0]
        vid = os.path.join(proj_dir(args.slug), "outputs", f"{name}.mp4")
        print(f"    - {name}  {'[montado]' if os.path.isfile(vid) else '[pendiente]'}")
    info = brand.get("info", {})
    if info:
        print(f"  info: {info.get('descripcion','')[:80]}")


def cmd_new_project(args):
    d = proj_dir(args.slug)
    if os.path.exists(d):
        sys.exit(f"Ya existe {d}.")
    for sub in ["pieces", "assets/characters", "assets/refs", "assets/screenshots", "assets/music", "outputs"]:
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    brand = {
        "slug": args.slug,
        "marca": {"nombre": args.slug.upper(), "tagline": "", "paleta": {"primario": "#E24B4A", "fondo": "#FAF6F1", "tinta": "#2C2C2C"}, "fuente": "Inter", "estilo_visual": ""},
        "salida": {"aspecto": "9:16", "resolucion": [1080, 1920], "fps": 30, "duracion_objetivo_s": 30,
                   "musica": {"tipo": "ambiental", "ruta": f"projects/{args.slug}/assets/music/bed.mp3"},
                   "voz_off": {"motor": "elevenlabs", "voz_id": "", "idioma": "es"}},
        "generacion": {"imagenes": {"motor": "openai", "modelo": "gpt-image-1", "calidad": "medium", "tamano": "1024x1536"}},
        "personajes": [],
        "info": {"descripcion": "", "publico": "", "propuesta_valor": [], "tono": "", "evitar": [], "enlaces": [], "notas": []},
    }
    json.dump(brand, open(os.path.join(d, "brand.json"), "w"), ensure_ascii=False, indent=2)
    print(f"Proyecto creado en {d}. Edita brand.json (marca, voz, info) y añade assets/.")


def cmd_new_piece(args):
    d = proj_dir(args.slug)
    if not os.path.isdir(d):
        sys.exit(f"No existe el proyecto {args.slug}.")
    dst = os.path.join(d, "pieces", f"{args.pieza}.json")
    if os.path.exists(dst):
        sys.exit(f"Ya existe {dst}.")
    if args.blueprint:
        bp = os.path.join("blueprints", f"{args.blueprint}.json")
        if not os.path.isfile(bp):
            sys.exit(f"No existe el blueprint {bp}. Disponibles: " +
                     ", ".join(os.path.splitext(os.path.basename(x))[0] for x in glob.glob("blueprints/*.json")))
        piece = json.load(open(bp)); piece["id"] = args.pieza
    else:
        piece = {"id": args.pieza, "concepto": "", "gancho": "", "cierre_marca": True, "segmentos": []}
    json.dump(piece, open(dst, "w"), ensure_ascii=False, indent=2)
    print(f"Pieza creada: {dst}" + (f" (desde blueprint {args.blueprint})" if args.blueprint else ""))


def cmd_produce(args):
    # Verificación previa (mismo gate que plan): no gastar GPU si hay bloqueos.
    if cmd_plan(args) != 0:
        sys.exit("⛔ Hay bloqueos en el plan. Resuélvelos antes de producir (ver arriba).")
    print("\n[produce] El gate ha pasado. La ejecución de fases A→J (pod + GPU) se conecta en la"
          " siguiente iteración del estudio; de momento usa el plan como contrato validado.\n"
          "Orden garantizado: A personajes → B imágenes → C voces → D música → E modelos →"
          " F clips GPU → G clips locales → H gate → I montaje → J entrega + apagar pod.")


def main():
    ap = argparse.ArgumentParser(description="Estudio de producción multi-empresa.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("plan");        sp.add_argument("slug"); sp.add_argument("pieza"); sp.set_defaults(f=cmd_plan)
    sp = sub.add_parser("status");      sp.add_argument("slug"); sp.set_defaults(f=cmd_status)
    sp = sub.add_parser("new-project"); sp.add_argument("slug"); sp.set_defaults(f=cmd_new_project)
    sp = sub.add_parser("new-piece");   sp.add_argument("slug"); sp.add_argument("pieza"); sp.add_argument("--blueprint"); sp.set_defaults(f=cmd_new_piece)
    sp = sub.add_parser("produce");     sp.add_argument("slug"); sp.add_argument("pieza"); sp.add_argument("--yes", action="store_true"); sp.set_defaults(f=cmd_produce)
    args = ap.parse_args()
    rc = args.f(args)
    sys.exit(rc or 0)


if __name__ == "__main__":
    main()
