#!/usr/bin/env python3
"""Generador robusto WAN t2v contra ComfyUI en RunPod.
Reintenta ante 403 intermitentes del proxy. Genera los items indicados,
espera por history, descarga el mp4. NO apaga el pod (eso lo hago aparte)."""
import json, time, sys, urllib.request, urllib.error, random

URL = "https://z1hteaxpp6eiv3-8188.proxy.runpod.net"
WF = "workflows/wan_t2v.json"
PROMPTS = "batch_prompts.json"
OUT = "outputs"

def req(path, data=None, timeout=60, retries=8):
    last = None
    for i in range(retries):
        try:
            r = urllib.request.Request(URL + path,
                data=json.dumps(data).encode() if data is not None else None,
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(r, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code in (403, 502, 503, 524):
                time.sleep(2 + i * 2 + random.random())
                continue
            raise
        except Exception as e:
            last = str(e)[:80]
            time.sleep(2 + i * 2)
    raise RuntimeError(f"req {path} agotó reintentos: {last}")

def build(item, wf_base):
    wf = json.loads(json.dumps(wf_base))
    seed = item.get("seed") or random.randint(1, 2**31)
    for nid, n in wf.items():
        ct = n.get("class_type")
        if ct == "CLIPTextEncode":
            if "Positive" in (n.get("_meta", {}).get("title", "")) or nid == "6":
                n["inputs"]["text"] = item["prompt"]
            else:
                n["inputs"]["text"] = item.get("negativo", "")
        elif ct == "EmptyHunyuanLatentVideo":
            n["inputs"]["width"] = item.get("width", 480)
            n["inputs"]["height"] = item.get("height", 832)
            n["inputs"]["length"] = item.get("frames", 81)
        elif ct == "KSampler":
            n["inputs"]["seed"] = seed
        elif ct == "VHS_VideoCombine":
            n["inputs"]["filename_prefix"] = item["id"]
    return wf, seed

def main(ids):
    wf_base = json.load(open(WF))
    items = [x for x in json.load(open(PROMPTS)) if x["id"] in ids]
    done = []
    for it in items:
        wf, seed = build(it, wf_base)
        print(f"[{it['id']}] encolando (seed={seed})...", flush=True)
        resp = json.loads(req("/prompt", {"prompt": wf}))
        pid = resp.get("prompt_id")
        print(f"  prompt_id={pid}", flush=True)
        # esperar history
        t0 = time.time()
        while time.time() - t0 < 900:
            time.sleep(8)
            try:
                h = json.loads(req(f"/history/{pid}", timeout=30))
            except Exception as e:
                print(f"  (poll retry: {e})", flush=True); continue
            if pid not in h:
                continue
            st = h[pid].get("status", {})
            if st.get("status_str") == "error":
                print(f"  ERROR generando {it['id']}", flush=True)
                break
            if st.get("completed"):
                outs = h[pid].get("outputs", {})
                fn = None
                for nid, o in outs.items():
                    for k in ("gifs", "videos", "images"):
                        for f in o.get(k, []):
                            if f.get("filename", "").endswith(".mp4"):
                                fn = f["filename"]
                if fn:
                    data = req(f"/view?filename={fn}&type=output", timeout=120)
                    path = f"{OUT}/{it['id']}.mp4"
                    open(path, "wb").write(data)
                    print(f"  ✅ DESCARGADO {path} ({len(data)} bytes)", flush=True)
                    done.append(path)
                break
    print(f"FIN. generados: {done}", flush=True)

if __name__ == "__main__":
    main(sys.argv[1:])
