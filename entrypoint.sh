#!/bin/bash
# Provision models then hand off to the stock RunPod ComfyUI start script.
# NOTE: no `set -e` — a model-download hiccup must not block ComfyUI/SSH/Jupyter
# from coming up (so the pod stays debuggable).

CO=/workspace/runpod-slim/ComfyUI

# On an ephemeral container the workspace is empty on each launch: seed it from
# the baked ComfyUI (which already contains our custom nodes + Silero + the
# userdata prompt template). /start.sh will then see an existing install.
if [ ! -d "$CO" ]; then
    echo "[entrypoint] seeding /workspace from baked ComfyUI..."
    cp -r /opt/comfyui-baked "$CO"
fi

# Fetch the InfiniteTalk model set (idempotent — skips files already present).
echo "[entrypoint] downloading models (this runs before ComfyUI starts)..."
python3.12 /download_models.py || echo "[entrypoint] WARN: model download returned non-zero; continuing"

echo "[entrypoint] handing off to /start.sh"
exec /start.sh
