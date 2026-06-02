# comfyui-infinitalk

Self-contained RunPod image for the InfiniteTalk talking-avatar engine
(ComfyUI + WanVideo/InfiniteTalk + MelBandRoFormer + Silero TTS).

Built **from** the official `runpod/comfyui:cuda12.8` base, so torch/CUDA/ComfyUI
are already present. Our custom nodes, the Silero `/silero_tts` route, and the
API prompt template are baked in; the model set is fetched at container start.

**Region-flexible:** no network volume — launches on any GPU in any region.

## One-time setup (≈10 min of your time, then CI does the rest)

1. Create a **new GitHub repo** named `comfyui-infinitalk` under your account
   (`Leo-AITeam`). Public is simplest.
2. Upload **all files in this folder** (keep the structure, including
   `.github/workflows/build-image.yml`).
3. GitHub Actions builds automatically on push and pushes the image to
   `ghcr.io/leo-aiteam/comfyui-infinitalk:latest` (watch the **Actions** tab; first
   build ≈ 5–15 min).
4. Make the package **public** so RunPod can pull it without credentials:
   GitHub → your profile → **Packages** → `comfyui-infinitalk` → *Package settings*
   → **Change visibility → Public**.

That's it. Tell me when the build is green and the package is public — I'll point
the n8n Launcher/Монтажёр at the image and we run the live test.

## Files
- `Dockerfile` — bakes custom nodes + Silero + prompt template onto the base.
- `entrypoint.sh` — seeds workspace, downloads models, hands off to stock `/start.sh`.
- `download_models.py` — idempotent model fetch (WanVideo / InfiniteTalk / VAE /
  LoRA / text-encoder / wav2vec2 / MelBandRoFormer / CLIP-vision).
- `custom_nodes/silero_tts_api/` — registers `POST /silero_tts` on the ComfyUI server.
- `infinitalk_prompt_api.json` — the 26-node API prompt (written to ComfyUI userdata).
- `.github/workflows/build-image.yml` — builds + pushes on every push to `main`.

## Notes
- Models download at each cold start (~30 GB, a few minutes on datacenter network).
  If cold-start speed matters later, we can bake the models into the image instead.
- ComfyUI becomes reachable on `:8188` only after models finish downloading, which
  is exactly what the launcher's readiness check waits for.
