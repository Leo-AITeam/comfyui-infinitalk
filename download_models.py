import os, shutil
from huggingface_hub import HfApi, hf_hub_download
CO="/workspace/runpod-slim/ComfyUI"; M=CO+"/models"
api=HfApi()
REPOS=["Kijai/WanVideo_comfy","Kijai/MelBandRoFormer_comfy","Kijai/wav2vec2_safetensors"]
FL={r:api.list_repo_files(r) for r in REPOS}
def find(opts):
    for r,fs in FL.items():
        for f in fs:
            if f.split('/')[-1].lower() in [o.lower() for o in opts]: return r,f
    for r,fs in FL.items():
        for f in fs:
            if f.endswith('.safetensors') and any(o.lower() in f.lower() for o in opts): return r,f
    return None,None
JOBS=[("diffusion_models",["Wan2_1-I2V-14B-480P_fp8_e4m3fn.safetensors"]),
("diffusion_models",["Wan2_1-InfiniTetalk-Single_fp16.safetensors","InfiniteTalk-Single"]),
("vae",["Wan2_1_VAE_bf16.safetensors"]),
("loras",["lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors"]),
("text_encoders",["umt5-xxl-enc-fp8_e4m3fn.safetensors"]),
("wav2vec2",["wav2vec2-chinese-base_fp16.safetensors","chinese-wav2vec2-base_fp16","wav2vec2-chinese"]),
("MelBandRoFormer",["MelBandRoformer_fp16.safetensors"])]
for folder,opts in JOBS:
    r,f=find(opts)
    if not r: print("MISSING",opts[0],flush=True); continue
    dest=os.path.join(M,folder); os.makedirs(dest,exist_ok=True)
    out=os.path.join(dest,os.path.basename(f))
    if os.path.exists(out): print("SKIP",out,flush=True); continue
    print("DL",r,f,flush=True)
    p=hf_hub_download(repo_id=r,filename=f,local_dir=dest)
    if os.path.abspath(p)!=os.path.abspath(out): shutil.move(p,out)
    print("OK",out,os.path.getsize(out)//1048576,"MB",flush=True)
cv=os.path.join(M,"clip_vision"); os.makedirs(cv,exist_ok=True)
cvout=os.path.join(cv,"clip_vision_h.safetensors")
if not os.path.exists(cvout):
    p=hf_hub_download(repo_id="Comfy-Org/Wan_2.1_ComfyUI_repackaged",filename="split_files/clip_vision/clip_vision_h.safetensors",local_dir=cv)
    if os.path.abspath(p)!=os.path.abspath(cvout): shutil.move(p,cvout)
    print("OK",cvout,flush=True)
mel=os.path.join(M,"MelBandRoFormer","MelBandRoformer_fp16.safetensors")
if os.path.exists(mel): shutil.copy(mel,os.path.join(M,"diffusion_models",os.path.basename(mel)))
print("ALL_MODELS_DONE",flush=True)
