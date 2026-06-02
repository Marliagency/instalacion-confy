#!/usr/bin/env python3
"""
run_i2v.py — Genera los clips WAN 2.2 image-to-video a partir de las imágenes
base (ya colocadas en la carpeta input de ComfyUI) y los descarga a ./outputs.

Construye un workflow nativo WAN 2.2 i2v en formato API (dos expertos MoE
high/low + LoRAs de destilado lightx2v para muestreo en 4 pasos) y lo encola
en ComfyUI por cada escena del lote. Espera por /history (polling, robusto) y
descarga el .mp4 por /view.

Uso:
    python3 run_i2v.py --comfy-url https://POD-8188.proxy.runpod.net \
        --prompts batch_prompts.json --out outputs
"""
import argparse, json, os, time, random, urllib.parse, urllib.request
import requests

I2V_HIGH = "wan2.2_i2v_high_noise_14B_fp16.safetensors"
I2V_LOW  = "wan2.2_i2v_low_noise_14B_fp16.safetensors"
LORA_HIGH = "i2v_lightx2v_high_noise_model.safetensors"
LORA_LOW  = "i2v_lightx2v_low_noise_model.safetensors"
CLIP = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
VAE  = "wan_2.1_vae.safetensors"  # 14B i2v usa el VAE de 16 canales (no el wan2.2_vae de 48ch, que es para el 5B)

def build(image, pos, neg, width, height, length, seed, prefix,
          steps=4, boundary=2, shift=8.0, fps=16):
    return {
        "1": {"class_type":"UNETLoader","inputs":{"unet_name":I2V_HIGH,"weight_dtype":"default"}},
        "2": {"class_type":"LoraLoaderModelOnly","inputs":{"model":["1",0],"lora_name":LORA_HIGH,"strength_model":1.0}},
        "3": {"class_type":"ModelSamplingSD3","inputs":{"model":["2",0],"shift":shift}},
        "4": {"class_type":"UNETLoader","inputs":{"unet_name":I2V_LOW,"weight_dtype":"default"}},
        "5": {"class_type":"LoraLoaderModelOnly","inputs":{"model":["4",0],"lora_name":LORA_LOW,"strength_model":1.0}},
        "6": {"class_type":"ModelSamplingSD3","inputs":{"model":["5",0],"shift":shift}},
        "7": {"class_type":"CLIPLoader","inputs":{"clip_name":CLIP,"type":"wan"}},
        "8": {"class_type":"CLIPTextEncode","inputs":{"text":pos,"clip":["7",0]}},
        "9": {"class_type":"CLIPTextEncode","inputs":{"text":neg,"clip":["7",0]}},
        "10":{"class_type":"VAELoader","inputs":{"vae_name":VAE}},
        "11":{"class_type":"LoadImage","inputs":{"image":image}},
        "12":{"class_type":"WanImageToVideo","inputs":{
                "positive":["8",0],"negative":["9",0],"vae":["10",0],
                "width":width,"height":height,"length":length,"batch_size":1,
                "start_image":["11",0]}},
        "13":{"class_type":"KSamplerAdvanced","inputs":{
                "model":["3",0],"add_noise":"enable","noise_seed":seed,"steps":steps,"cfg":1.0,
                "sampler_name":"euler","scheduler":"simple","positive":["12",0],"negative":["12",1],
                "latent_image":["12",2],"start_at_step":0,"end_at_step":boundary,
                "return_with_leftover_noise":"enable"}},
        "14":{"class_type":"KSamplerAdvanced","inputs":{
                "model":["6",0],"add_noise":"disable","noise_seed":seed,"steps":steps,"cfg":1.0,
                "sampler_name":"euler","scheduler":"simple","positive":["12",0],"negative":["12",1],
                "latent_image":["13",0],"start_at_step":boundary,"end_at_step":steps,
                "return_with_leftover_noise":"disable"}},
        "15":{"class_type":"VAEDecode","inputs":{"samples":["14",0],"vae":["10",0]}},
        "16":{"class_type":"VHS_VideoCombine","inputs":{
                "images":["15",0],"frame_rate":fps,"loop_count":0,"filename_prefix":prefix,
                "format":"video/h264-mp4","pingpong":False,"save_output":True}},
    }

def queue(base, wf):
    r=requests.post(f"{base}/prompt", json={"prompt":wf}, timeout=60)
    if r.status_code>=400:
        raise RuntimeError(f"/prompt HTTP {r.status_code}: {r.text[:600]}")
    return r.json()["prompt_id"]

def wait(base, pid, timeout=1800, interval=5):
    t0=time.time()
    while time.time()-t0<timeout:
        h=requests.get(f"{base}/history/{pid}", timeout=30).json()
        if pid in h:
            st=h[pid].get("status",{})
            if st.get("status_str")=="error" or st.get("completed") is False and st.get("status_str")=="error":
                raise RuntimeError(f"ejecución error: {json.dumps(st)[:400]}")
            if h[pid].get("outputs"):
                return h[pid]["outputs"]
        time.sleep(interval)
    raise TimeoutError(f"timeout esperando {pid}")

def download(base, outputs, out_dir, vid):
    saved=[]
    s=requests.Session(); s.headers.update({"User-Agent":"Mozilla/5.0"})  # el proxy de RunPod exige UA
    for node in outputs.values():
        for key in ("gifs","videos"):  # solo el vídeo final, no frames sueltos
            for it in node.get(key,[]):
                fn=it.get("filename")
                if not fn or not fn.endswith((".mp4",".webm",".gif")):
                    continue
                params=urllib.parse.urlencode({"filename":fn,"subfolder":it.get("subfolder",""),"type":it.get("type","output")})
                r=s.get(f"{base}/view?{params}", timeout=180); r.raise_for_status()
                local=os.path.join(out_dir,f"{vid}.mp4")
                open(local,"wb").write(r.content)
                saved.append(local)
    return saved

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--comfy-url",required=True)
    ap.add_argument("--prompts",required=True)
    ap.add_argument("--out",default="outputs")
    ap.add_argument("--width",type=int,default=480)
    ap.add_argument("--height",type=int,default=832)
    ap.add_argument("--length",type=int,default=81)
    args=ap.parse_args()
    base=args.comfy_url.rstrip("/")
    os.makedirs(args.out,exist_ok=True)
    items=json.load(open(args.prompts))
    ok,fail=[],[]
    for i,it in enumerate(items,1):
        iid=it["id"]; img=f"{iid}.png"
        seed=it.get("seed") or random.randint(0,2**31-1)
        neg=it.get("negativo","blurry, low quality, distorted, watermark, text")
        wf=build(img, it["prompt"], neg, it.get("width",args.width), it.get("height",args.height),
                 it.get("frames",args.length), seed, iid)
        print(f"[{i}/{len(items)}] {iid} encolando (seed {seed})...", flush=True)
        try:
            pid=queue(base,wf)
            outs=wait(base,pid)
            saved=download(base,outs,args.out,iid)
            print(f"   OK -> {[os.path.basename(s) for s in saved]}", flush=True)
            ok.append(iid)
        except Exception as e:
            print(f"   ERROR: {e}", flush=True)
            fail.append({"id":iid,"error":str(e)})
    print(f"\nRESUMEN i2v: OK={len(ok)} FAIL={len(fail)}")
    for f in fail: print("  -",f["id"],f["error"][:200])

if __name__=="__main__":
    main()
