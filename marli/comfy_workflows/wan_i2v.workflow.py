import json, urllib.request, ssl, time, urllib.parse
ctx=ssl._create_unverified_context()
URL="https://av30vjc1y4ex6b-8188.proxy.runpod.net"; UA="Mozilla/5.0 Chrome/120"
def post(p,data): return urllib.request.urlopen(urllib.request.Request(URL+p,data=json.dumps(data).encode(),headers={"User-Agent":UA,"Content-Type":"application/json"}),timeout=60,context=ctx)
def get(p): return json.loads(urllib.request.urlopen(urllib.request.Request(URL+p,headers={"User-Agent":UA}),timeout=60,context=ctx).read())
mp="the young woman talks naturally to the camera, subtle natural handheld movement, blinking, slight warm smile, gentle breathing"
wf={
 "1":{"class_type":"UNETLoader","inputs":{"unet_name":"Wan2.1/wan2.1_i2v_480p_14B_fp8_scaled.safetensors","weight_dtype":"default"}},
 "2":{"class_type":"CLIPLoader","inputs":{"clip_name":"umt5_xxl_fp8_e4m3fn_scaled.safetensors","type":"wan"}},
 "3":{"class_type":"VAELoader","inputs":{"vae_name":"wan_2.1_vae.safetensors"}},
 "4":{"class_type":"CLIPVisionLoader","inputs":{"clip_name":"CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors"}},
 "11":{"class_type":"LoadImage","inputs":{"image":"beat1_hook.png"}},
 "12":{"class_type":"CLIPVisionEncode","inputs":{"clip_vision":["4",0],"image":["11",0],"crop":"center"}},
 "5":{"class_type":"CLIPTextEncode","inputs":{"clip":["2",0],"text":mp}},
 "6":{"class_type":"CLIPTextEncode","inputs":{"clip":["2",0],"text":"static, still, distorted, blurry, low quality, extra limbs"}},
 "13":{"class_type":"WanImageToVideo","inputs":{"positive":["5",0],"negative":["6",0],"vae":["3",0],"width":480,"height":832,"length":49,"batch_size":1,"clip_vision_output":["12",0],"start_image":["11",0]}},
 "14":{"class_type":"ModelSamplingSD3","inputs":{"shift":8.0,"model":["1",0]}},
 "8":{"class_type":"KSampler","inputs":{"seed":42,"steps":25,"cfg":6.0,"sampler_name":"uni_pc","scheduler":"simple","denoise":1.0,"model":["14",0],"positive":["13",0],"negative":["13",1],"latent_image":["13",2]}},
 "9":{"class_type":"VAEDecode","inputs":{"samples":["8",0],"vae":["3",0]}},
 "10":{"class_type":"VHS_VideoCombine","inputs":{"images":["9",0],"frame_rate":16,"loop_count":0,"filename_prefix":"wani","format":"video/h264-mp4","pingpong":False,"save_output":True}}
}
t=time.time()
try: pid=json.loads(post("/prompt",{"prompt":wf,"client_id":"w"}).read())["prompt_id"]; print("queued",pid)
except urllib.error.HTTPError as e: print("ERR",e.code,e.read()[:500].decode()); raise SystemExit
for _ in range(160):
    h=get(f"/history/{pid}").get(pid)
    if h:
        st=h.get("status",{})
        if st.get("status_str")=="error": print("ERROR",json.dumps(st)[:600]); break
        vid=None
        for n in h.get("outputs",{}).values():
            for g in n.get("gifs",[])+n.get("videos",[]): vid=g
        if vid:
            q=urllib.parse.urlencode({"filename":vid["filename"],"subfolder":vid.get("subfolder",""),"type":vid.get("type","output")})
            open("/tmp/wantest.mp4","wb").write(urllib.request.urlopen(urllib.request.Request(URL+"/view?"+q,headers={"User-Agent":UA}),timeout=180,context=ctx).read())
            print("OK %.0fs"%(time.time()-t)); break
        if st.get("completed"): print("done no vid", json.dumps(h.get("outputs",{}))[:200]); break
    time.sleep(4)
