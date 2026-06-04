#!/usr/bin/env python3
"""
ui2api.py — Convierte un workflow ComfyUI de formato UI a formato API.

Maneja: enlaces explícitos (links), valores de widgets (mapeados con /object_info),
y los nodos virtuales Set/Get de KJNodes (resuelve GetNode -> fuente del SetNode).
Pensado para reutilizar los workflows de ejemplo de kijai (p.ej. InfiniteTalk) sin
montarlos a mano. Se ejecuta donde haya acceso a /object_info (in-pod).

Uso (como módulo): from ui2api import convert; api = convert(ui_json, object_info)
"""
import json

VIRTUAL = {"Note", "MarkdownNote", "Reroute", "SetNode", "GetNode",
           "PrimitiveNode", "Anything Everywhere", "Anything Everywhere3",
           "Prompts Everywhere", "Seed Everywhere"}


def _widget_inputs(oi, ctype):
    """Inputs que son widgets (combo/escalares), en orden, para alinear widgets_values."""
    spec = oi.get(ctype, {}).get("input", {})
    out = []
    for grp in ("required", "optional"):
        for k, v in (spec.get(grp) or {}).items():
            t = v[0]
            if isinstance(t, list) or t in ("INT", "FLOAT", "STRING", "BOOLEAN"):
                out.append((k, t))
    return out


def convert(ui, oi):
    nodes = {n["id"]: n for n in ui["nodes"]}
    links = {l[0]: l for l in ui.get("links", [])}  # id -> [id,from,from_slot,to,to_slot,type]

    # mapa SetNode: nombre -> (nodo_fuente, slot_fuente)
    setmap = {}
    for n in ui["nodes"]:
        if n.get("type") == "SetNode":
            nm = (n.get("widgets_values") or ["?"])[0]
            inp = (n.get("inputs") or [{}])[0]
            lk = inp.get("link")
            if lk in links:
                l = links[lk]; setmap[nm] = (l[1], l[2])

    def resolve(node_id, slot):
        n = nodes.get(node_id)
        if n and n.get("type") == "GetNode":
            nm = (n.get("widgets_values") or ["?"])[0]
            return setmap.get(nm, (node_id, slot))
        return (node_id, slot)

    api = {}
    for n in ui["nodes"]:
        t = n.get("type")
        if t in VIRTUAL:
            continue
        inputs = {}
        # conexiones
        for inp in (n.get("inputs") or []):
            lk = inp.get("link")
            if lk in links:
                l = links[lk]
                src = resolve(l[1], l[2])
                # si la fuente quedó en un nodo virtual no resuelto, omitir
                if nodes.get(src[0], {}).get("type") in VIRTUAL:
                    continue
                inputs[inp["name"]] = [str(src[0]), src[1]]
        # widgets
        wv = n.get("widgets_values")
        if isinstance(wv, list):
            wi = 0
            for (name, typ) in _widget_inputs(oi, t):
                if wi >= len(wv):
                    break
                inputs[name] = wv[wi]; wi += 1
                if name in ("seed", "noise_seed") and wi < len(wv) and \
                        wv[wi] in ("fixed", "increment", "decrement", "randomize"):
                    wi += 1
        elif isinstance(wv, dict):
            for k, val in wv.items():
                inputs.setdefault(k, val)
        api[str(n["id"])] = {"class_type": t, "inputs": inputs}
    return api


if __name__ == "__main__":
    import argparse, requests
    ap = argparse.ArgumentParser()
    ap.add_argument("ui_json")
    ap.add_argument("--comfy-url", default="http://127.0.0.1:8188")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    oi = requests.get(args.comfy_url.rstrip("/") + "/object_info", timeout=120).json()
    api = convert(json.load(open(args.ui_json)), oi)
    json.dump(api, open(args.out, "w"), indent=2)
    print(f"convertido -> {args.out} ({len(api)} nodos)")
