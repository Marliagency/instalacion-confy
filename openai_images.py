#!/usr/bin/env python3
"""
openai_images.py — Genera las imágenes base del lote con la API de OpenAI.

Encaja en el pipeline así:

    BRIEF  ->  batch_prompts.json  ->  [openai_images.py]  ->  outputs/images/*.png
                                                                      │
                                                       (imagen base por clip)
                                                                      ▼
                                            WAN image-to-video (comfy_batch.py)
                                                                      ▼
                                                  edit_video.py (montaje final)

Lee el MISMO `batch_prompts.json` que usa el resto del pipeline y genera UNA
imagen por item con gpt-image-1. Para items de tipo "video" la imagen sirve de
fotograma inicial para WAN image-to-video; para items "imagen" es la entrega
final. Guarda cada PNG como outputs/images/<id>.png.

Requisitos:
    - Variable de entorno OPENAI_API_KEY.
    - Acceso de red a api.openai.com (allowlist del entorno: añadir api.openai.com).

Uso:
    python3 openai_images.py --prompts ./batch_prompts.json --out ./outputs/images
    python3 openai_images.py --prompts ./batch_prompts.json --only video   # solo bases de video
    python3 openai_images.py --prompts ./batch_prompts.json --dry-run       # no llama a la API

Solo usa la librería estándar (urllib): no necesita instalar nada.
"""

import argparse
import base64
import json
import os
import sys
import time
import urllib.request
import urllib.error

API_URL = "https://api.openai.com/v1/images/generations"

# gpt-image-1 solo admite estos tamaños. Elegimos el más cercano al formato
# pedido en cada item (el aspecto se afina luego en el montaje/animación).
SIZES = {
    "vertical": "1024x1536",    # ~9:16, redes (por defecto para 9:16 / 2:3 / 3:4)
    "horizontal": "1536x1024",  # ~16:9
    "cuadrado": "1024x1024",    # 1:1
}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def pick_size(item):
    """Mapea el 'formato'/width/height del item al tamaño soportado más cercano."""
    fmt = str(item.get("formato", "")).strip()
    w = item.get("width")
    h = item.get("height")
    if fmt in ("1:1",) or (w and h and abs(w - h) <= 1):
        return SIZES["cuadrado"]
    if fmt in ("16:9", "16x9") or (w and h and w > h):
        return SIZES["horizontal"]
    # 9:16, 2:3, 3:4, vertical, o desconocido -> vertical (caso más común en redes)
    return SIZES["vertical"]


EDITS_URL = "https://api.openai.com/v1/images/edits"


def _multipart(fields, files):
    """Codifica multipart/form-data. files = [(fieldname, path), …]."""
    import mimetypes, uuid
    boundary = uuid.uuid4().hex
    body = b""
    for k, v in fields.items():
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n").encode()
    for field, path in files:
        fn = os.path.basename(path)
        ctype = mimetypes.guess_type(path)[0] or "image/png"
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; "
                 f"filename=\"{fn}\"\r\nContent-Type: {ctype}\r\n\r\n").encode()
        body += open(path, "rb").read() + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def generate_image(prompt, size, api_key, quality="medium", model="gpt-image-1",
                   ref_paths=None, timeout=300, retries=3):
    """Genera (o EDITA, si hay referencias) una imagen y devuelve los bytes PNG.

    Con `ref_paths` usa la API de edición (image-to-image) para PRESERVAR la
    mascota/producto de referencia (R7); si no, generación normal."""
    refs = [p for p in (ref_paths or []) if os.path.isfile(p)]
    if refs:
        fields = {"model": model, "prompt": prompt, "size": size, "quality": quality, "n": "1"}
        body, ctype = _multipart(fields, [("image[]", p) for p in refs])
        url, headers = EDITS_URL, {"Authorization": f"Bearer {api_key}", "Content-Type": ctype}
    else:
        body = json.dumps({"model": model, "prompt": prompt, "size": size,
                           "quality": quality, "n": 1}).encode("utf-8")
        url, headers = API_URL, {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return base64.b64decode(data["data"][0]["b64_json"])
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:500]}"
            if 400 <= e.code < 500 and e.code != 429:
                break
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Falló la generación de imagen: {last_err}")


def main():
    ap = argparse.ArgumentParser(description="Genera imágenes base con la API de OpenAI (gpt-image-1).")
    ap.add_argument("--prompts", help="JSON de lote plano (id/prompt/...) — modo legacy")
    ap.add_argument("--package", help="Paquete de producción (schema/production_package). Aplana imágenes por segmento.")
    ap.add_argument("--out", default="./outputs/images", help="Carpeta de salida de los PNG")
    ap.add_argument("--only", choices=["video", "imagen"], help="(modo --prompts) generar solo bases de un tipo")
    ap.add_argument("--model", default="gpt-image-1", help="Modelo OpenAI (gpt-image-1, gpt-image-1-mini si está disponible)")
    ap.add_argument("--quality", default="medium", choices=["low", "medium", "high"], help="Calidad (medium = económico)")
    ap.add_argument("--dry-run", action="store_true", help="No llama a la API; solo muestra qué generaría")
    ap.add_argument("--concurrency", type=int, default=6, help="Imágenes en paralelo (clave para volumen)")
    args = ap.parse_args()

    if args.package:
        import pipeline
        pkg = pipeline.load_package(args.package)
        gen = pkg.get("generacion", {}).get("imagenes", {})
        if gen.get("modelo"): args.model = gen["modelo"]
        if gen.get("calidad"): args.quality = gen["calidad"]
        items = [{"id": it["id"], "prompt": it["prompt"], "negativo": it["negativo"],
                  "referencias": it.get("referencias") or [],
                  "formato": pkg["salida"]["aspecto"]} for it in pipeline.iter_image_items(pkg)]
        # el tamaño ya viene resuelto por aspecto; pick_size lo recalcula igual
    elif args.prompts:
        items = load_json(args.prompts)
    else:
        sys.exit("Pasa --package (recomendado) o --prompts.")
    if not isinstance(items, list) or not items:
        sys.exit("No hay items que generar.")
    if args.only:
        items = [it for it in items if (it.get("tipo") or "video").lower() == args.only]
        if not items:
            sys.exit(f"No hay items de tipo '{args.only}' en el lote.")

    api_key = os.environ.get("OPENAI_API_KEY")
    if not args.dry_run and not api_key:
        sys.exit("ERROR: falta OPENAI_API_KEY en el entorno. Añádela y reabre la sesión.")

    os.makedirs(args.out, exist_ok=True)
    ok, fail = [], []
    t0 = time.time()

    if args.dry_run:
        for i, item in enumerate(items, 1):
            iid = item.get("id", f"img{i:02d}")
            print(f"[{i}/{len(items)}] {iid} ({pick_size(item)}): {(item.get('prompt') or '')[:80]}")
            (ok if item.get("prompt") else fail).append(iid if item.get("prompt") else {"id": iid, "error": "sin prompt"})
        dt = time.time() - t0
        print(f"\n(dry-run) {len(ok)} imágenes se generarían. Sin gasto.")
        return

    def work(item, i):
        iid = item.get("id", f"img{i:02d}")
        prompt = item.get("prompt")
        if not prompt:
            return iid, None, "sin prompt"
        try:
            png = generate_image(prompt, pick_size(item), api_key, quality=args.quality,
                                 model=args.model, ref_paths=item.get("referencias"))
            with open(os.path.join(args.out, f"{iid}.png"), "wb") as f:
                f.write(png)
            return iid, len(png), None
        except Exception as e:  # noqa: BLE001
            return iid, None, str(e)

    import concurrent.futures
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as ex:
        futs = {ex.submit(work, it, i): i for i, it in enumerate(items, 1)}
        for fut in concurrent.futures.as_completed(futs):
            iid, n, err = fut.result(); done += 1
            if err:
                print(f"[{done}/{len(items)}] {iid}  ERROR: {err}", flush=True)
                fail.append({"id": iid, "error": err})
            else:
                print(f"[{done}/{len(items)}] {iid}  OK ({n//1024} KB)", flush=True)
                ok.append(iid)

    dt = time.time() - t0
    print(f"\n===== IMÁGENES (OpenAI) =====")
    print(f"OK: {len(ok)}  Fallos: {len(fail)}  Tiempo: {dt:.0f}s")
    if fail:
        for f in fail:
            print(f"  - {f['id']}: {f['error']}")
    if args.dry_run:
        print("\n(dry-run: no se llamó a la API ni se gastaron créditos de OpenAI)")


if __name__ == "__main__":
    main()
