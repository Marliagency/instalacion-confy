#!/usr/bin/env python3
"""Generador de imágenes con OpenAI gpt-image-1 (reemplaza a Gemini/Qwen para
los stills de referencia del pipeline de Marli).

Sin dependencias externas (urllib). La API key se lee de marli/.secrets
(línea `OPENAI_API_KEY=sk-...`) o de la variable de entorno OPENAI_API_KEY.

Dos modos:
  generate : texto -> imagen
  edit     : imagen(es) de referencia + texto -> imagen   (para colocar a Li
             en una escena o mantener una cara UGC consistente)

Ejemplos:
  # Escena UGC desde cero (vertical 9:16 aprox)
  python3 marli/openai_image.py generate \
      --prompt "Selfie UGC de una psicóloga sonriente en su consulta luminosa,
                luz natural de ventana, estética iPhone, 9:16" \
      --size 1024x1536 --quality high --out marli/assets/scenes/ugc_psico.png

  # Meter a Li (referencia) en una escena nueva
  python3 marli/openai_image.py edit \
      --ref marli/assets/li_ref.png \
      --prompt "El robot rojo Li sobre un escritorio de consulta de psicología,
                fondo cálido desenfocado, foto realista, 9:16" \
      --size 1024x1536 --quality high --out marli/assets/scenes/li_escena.png

Tamaños válidos: 1024x1024, 1024x1536 (vertical), 1536x1024 (horizontal).
Calidad: low | medium | high  (low es la más barata para iterar prompts).
"""
import argparse, base64, json, os, sys, urllib.request, urllib.error, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
API = "https://api.openai.com/v1"


def load_key():
    k = os.environ.get("OPENAI_API_KEY")
    if k:
        return k.strip()
    sec = os.path.join(HERE, ".secrets")
    if os.path.exists(sec):
        for line in open(sec):
            line = line.strip()
            if line.startswith("OPENAI_API_KEY"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("No hay API key. Pon OPENAI_API_KEY=sk-... en marli/.secrets o en el entorno.")


def _save_b64(resp_bytes, out):
    data = json.loads(resp_bytes)
    if "data" not in data:
        sys.exit("Respuesta inesperada de OpenAI:\n" + json.dumps(data, indent=2)[:1200])
    b64 = data["data"][0]["b64_json"]
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    open(out, "wb").write(base64.b64decode(b64))
    use = data.get("usage", {})
    print(f"OK -> {out}   (tokens: {use})")


def generate(key, prompt, size, quality, out):
    body = json.dumps({"model": "gpt-image-1", "prompt": prompt,
                       "size": size, "quality": quality, "n": 1}).encode()
    req = urllib.request.Request(API + "/images/generations", data=body,
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    try:
        _save_b64(urllib.request.urlopen(req, timeout=300).read(), out)
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode()[:1200]}")


def _multipart(fields, files):
    """fields: dict[str,str]; files: list[(field, path)]. Devuelve (body, content_type)."""
    boundary = "----marliboundary" + uuid.uuid4().hex
    nl = b"\r\n"
    buf = b""
    for k, v in fields.items():
        buf += b"--" + boundary.encode() + nl
        buf += f'Content-Disposition: form-data; name="{k}"'.encode() + nl + nl
        buf += str(v).encode() + nl
    for field, path in files:
        fn = os.path.basename(path)
        buf += b"--" + boundary.encode() + nl
        buf += f'Content-Disposition: form-data; name="{field}"; filename="{fn}"'.encode() + nl
        buf += b"Content-Type: image/png" + nl + nl
        buf += open(path, "rb").read() + nl
    buf += b"--" + boundary.encode() + b"--" + nl
    return buf, f"multipart/form-data; boundary={boundary}"


def edit(key, prompt, refs, size, quality, out):
    fields = {"model": "gpt-image-1", "prompt": prompt, "size": size,
              "quality": quality, "n": "1"}
    # gpt-image-1 admite varias imágenes de referencia con el campo "image[]"
    files = [("image[]", r) for r in refs]
    body, ctype = _multipart(fields, files)
    req = urllib.request.Request(API + "/images/edits", data=body,
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": ctype})
    try:
        _save_b64(urllib.request.urlopen(req, timeout=300).read(), out)
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode()[:1200]}")


def main():
    ap = argparse.ArgumentParser(description="Imágenes con OpenAI gpt-image-1")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("generate", "edit"):
        p = sub.add_parser(name)
        p.add_argument("--prompt", required=True)
        p.add_argument("--out", required=True)
        p.add_argument("--size", default="1024x1536",
                       choices=["1024x1024", "1024x1536", "1536x1024"])
        p.add_argument("--quality", default="high", choices=["low", "medium", "high"])
        if name == "edit":
            p.add_argument("--ref", action="append", required=True,
                           help="ruta a imagen de referencia (repetible)")
    args = ap.parse_args()
    key = load_key()
    if args.cmd == "generate":
        generate(key, args.prompt, args.size, args.quality, args.out)
    else:
        edit(key, args.prompt, args.ref, args.size, args.quality, args.out)


if __name__ == "__main__":
    main()
