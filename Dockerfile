# ===========================================================================
# comfyui-infinitalk — self-contained, region-flexible InfiniteTalk engine
# Base: official RunPod ComfyUI (Ubuntu 24.04 + Py3.12 + CUDA 12.8 + torch 2.10,
#       ComfyUI v0.18.2 baked at /opt/comfyui-baked, entrypoint /start.sh).
# We bake our custom nodes + Silero TTS + the API prompt template into the
# baked ComfyUI, and use our own entrypoint to fetch models then hand off to
# the stock /start.sh.  Models are pulled at container start (image stays light;
# datacenter download is fast). No network volume, launches in ANY region.
# ===========================================================================
FROM runpod/comfyui:cuda12.8

# --- 0. Ensure ffmpeg + ffprobe (for /render_movie assembly) ---
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

# --- 1. Custom nodes, baked so /start.sh copies them to /workspace on launch ---
RUN cd /opt/comfyui-baked/custom_nodes && \
    git clone --depth 1 https://github.com/kijai/ComfyUI-WanVideoWrapper && \
    git clone --depth 1 https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite && \
    git clone --depth 1 https://github.com/kijai/ComfyUI-MelBandRoFormer

# --- 2. Python deps into SYSTEM site-packages (runtime venv uses --system-site-packages) ---
RUN python3.12 -m pip install --no-cache-dir \
      -r /opt/comfyui-baked/custom_nodes/ComfyUI-WanVideoWrapper/requirements.txt \
      -r /opt/comfyui-baked/custom_nodes/ComfyUI-VideoHelperSuite/requirements.txt \
      -r /opt/comfyui-baked/custom_nodes/ComfyUI-MelBandRoFormer/requirements.txt && \
    python3.12 -m pip install --no-cache-dir num2words omegaconf huggingface_hub

# --- 2b. Pre-load Silero model at build (trust_repo, cached into image) ---
RUN python3.12 -c "import torch; torch.hub.load('snakers4/silero-models','silero_tts',language='ru',speaker='v4_ru',trust_repo=True)"

# --- 3. Silero TTS API custom node (registers POST /silero_tts on ComfyUI server) ---
COPY custom_nodes/silero_tts_api /opt/comfyui-baked/custom_nodes/silero_tts_api
COPY custom_nodes/render_movie_api /opt/comfyui-baked/custom_nodes/render_movie_api

# --- 4. Baked API prompt template (ComfyUI userdata) ---
RUN mkdir -p /opt/comfyui-baked/user/default
COPY infinitalk_prompt_api.json /opt/comfyui-baked/user/default/infinitalk_prompt_api.json

# --- 5. Model downloader + our entrypoint wrapper ---
COPY download_models.py /download_models.py
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Our entrypoint provisions models, then execs the stock /start.sh
ENTRYPOINT ["/entrypoint.sh"]
