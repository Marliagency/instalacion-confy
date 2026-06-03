#!/usr/bin/env python3
"""
manifest.py — Escribe outptus/manifest.json: el inventario del banco de assets.

Lo genera la S2 al terminar; lo consume la S3 (editor) para revisar y seleccionar.
Ata cada asset a su intención del guion (pieza, segmento, formato, qué dice / texto).

    python3 manifest.py --package production_package.json --dir outputs
"""
import argparse, json, os
import pipeline


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", required=True)
    ap.add_argument("--dir", default="outputs")
    args = ap.parse_args()
    pkg = pipeline.load_package(args.package)
    d = args.dir
    assets = []

    for it in pipeline.iter_image_items(pkg):
        p = os.path.join(d, "images", f"{it['id']}.png")
        assets.append({"tipo": "image", "uid": it["uid"], "id": it["id"],
                       "pieza": it["pieza_id"], "segmento": it["seg_id"],
                       "formato": it["formato"], "idx": it["idx"],
                       "path": p, "exists": os.path.isfile(p)})

    for s in pipeline.iter_segments(pkg):
        seg = s["seg"]; uid = s["uid"]
        dice = (seg.get("avatar") or {}).get("dialogo") or seg.get("voz_off")
        clip = os.path.join(d, "clips", f"{uid}.mp4")
        assets.append({"tipo": "clip", "uid": uid, "pieza": s["pieza_id"],
                       "segmento": s["id"], "formato": s["formato"], "motor": s["engine"],
                       "orden": s["seg_order"], "dice": dice,
                       "texto_pantalla": seg.get("texto_pantalla"),
                       "path": clip, "exists": os.path.isfile(clip)})
        for suf, sub in ((".mp3", "avatar"), ("_vo.mp3", "voz_off")):
            vp = os.path.join(d, "voice", f"{uid}{suf}")
            if os.path.isfile(vp):
                assets.append({"tipo": "voice", "subtipo": sub, "uid": uid,
                               "pieza": s["pieza_id"], "segmento": s["id"],
                               "path": vp, "exists": True})

    out = os.path.join(d, "manifest.json")
    os.makedirs(d, exist_ok=True)
    json.dump({"package": args.package, "assets": assets}, open(out, "w"),
              ensure_ascii=False, indent=2)
    n = {t: sum(1 for a in assets if a["tipo"] == t) for t in ("image", "clip", "voice")}
    miss = [a["path"] for a in assets if not a.get("exists")]
    print(f"manifest -> {out}  (imágenes {n['image']}, clips {n['clip']}, voces {n['voice']})")
    if miss:
        print(f"  AVISO: {len(miss)} assets aún no generados:")
        for m in miss[:10]: print("   -", m)


if __name__ == "__main__":
    main()
