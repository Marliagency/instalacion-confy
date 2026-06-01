import json, urllib.request, ssl, time, uuid, urllib.parse
ctx=ssl._create_unverified_context()
URL="https://av30vjc1y4ex6b-8188.proxy.runpod.net"; UA="Mozilla/5.0 Chrome/120"
def post(p,data):
    return urllib.request.urlopen(urllib.request.Request(URL+p,data=json.dumps(data).encode(),headers={"User-Agent":UA,"Content-Type":"application/json"}),timeout=60,context=ctx)
def get(p):
    return json.loads(urllib.request.urlopen(urllib.request.Request(URL+p,headers={"User-Agent":UA}),timeout=60,context=ctx).read())
wf={
 "1":{"class_type":"UNETLoader","inputs":{"unet_name":"qwen-image/qwen_image_fp8_e4m3fn.safetensors","weight_dtype":"default"}},
 "2":{"class_type":"CLIPLoader","inputs":{"clip_name":"qwen/qwen_2.5_vl_7b_fp8_scaled.safetensors","type":"qwen_image"}},
 "3":{"class_type":"VAELoader","inputs":{"vae_name":"qwen-image/qwen_image_vae.safetensors"}},
 "4":{"class_type":"ModelSamplingAuraFlow","inputs":{"shift":3.1,"model":["1",0]}},
 "5":{"class_type":"CLIPTextEncode","inputs":{"clip":["2",0],"text":"Cinematic photo, a tired female psychologist at night sitting at her desk, overwhelmed, surrounded by tall stacks of paper reports and folders, a single warm desk lamp, moody atmosphere, cream and amber tones, shallow depth of field, premium editorial, photorealistic, vertical composition"}},
 "6":{"class_type":"CLIPTextEncode","inputs":{"clip":["2",0],"text":"low quality, blurry, deformed, extra fingers, text, watermark, cartoon, ugly"}},
 "7":{"class_type":"EmptySD3LatentImage","inputs":{"width":896,"height":1152,"batch_size":1}},
 "8":{"class_type":"KSampler","inputs":{"seed":42,"steps":20,"cfg":2.5,"sampler_name":"euler","scheduler":"simple","denoise":1.0,"model":["4",0],"positive":["5",0],"negative":["6",0],"latent_image":["7",0]}},
 "9":{"class_type":"VAEDecode","inputs":{"samples":["8",0],"vae":["3",0]}},
 "10":{"class_type":"SaveImage","inputs":{"filename_prefix":"qtest","images":["9",0]}}
}
t=time.time(); pid=json.loads(post("/prompt",{"prompt":wf,"client_id":"q"}).read())["prompt_id"]; print("queued",pid)
for _ in range(120):
    h=get(f"/history/{pid}").get(pid)
    if h:
        st=h.get("status",{})
        if st.get("status_str")=="error": print("ERROR", json.dumps(h.get("status",{}))[:400]); break
        outs=h.get("outputs",{})
        img=None
        for n in outs.values():
            for im in n.get("images",[]): img=im
        if img:
            q=urllib.parse.urlencode({"filename":img["filename"],"subfolder":img.get("subfolder",""),"type":img.get("type","output")})
            open("/tmp/qtest.png","wb").write(urllib.request.urlopen(urllib.request.Request(URL+"/view?"+q,headers={"User-Agent":UA}),timeout=120,context=ctx).read())
            print("OK %.0fs"%(time.time()-t)); break
        if st.get("completed"): print("done no img"); break
    time.sleep(3)
