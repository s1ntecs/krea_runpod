#!/usr/bin/env bash
set -Eeuo pipefail

export PYTHONPATH="/opt/krea/src${PYTHONPATH:+:${PYTHONPATH}}"
: "${MODEL_ROOT:=/runpod-volume/models}"
: "${OUTPUT_ROOT:=/tmp/krea-comfy-output}"
: "${MODEL_MANIFEST:=/opt/krea/config/models.json}"
: "${LORA_CATALOG:=/opt/krea/config/lora_catalog.json}"
: "${COMFY_HOST:=127.0.0.1}"
: "${COMFY_PORT:=8188}"
: "${AUTO_DOWNLOAD_MODELS:=false}"
: "${VERIFY_MODEL_SHA256:=false}"
: "${PRELOAD_FILE_CACHE:=true}"
: "${WARMUP_ON_START:=false}"
: "${COMFY_LOG_LEVEL:=INFO}"

mkdir -p \
  "$MODEL_ROOT/diffusion_models" \
  "$MODEL_ROOT/text_encoders" \
  "$MODEL_ROOT/vae" \
  "$MODEL_ROOT/loras" \
  "$OUTPUT_ROOT"

echo "Checking NVIDIA GPU and PyTorch CUDA runtime"
python - <<'PYGPU'
import torch

if not torch.cuda.is_available():
    raise SystemExit("CUDA is not available inside the worker")
torch.cuda.init()
probe = (torch.ones(8, device="cuda") + 1).sum().item()
torch.cuda.synchronize()
name = torch.cuda.get_device_name(0)
capability = torch.cuda.get_device_capability(0)
print(
    f"GPU ready: {name}; sm_{capability[0]}{capability[1]}; "
    f"torch={torch.__version__}; cuda={torch.version.cuda}; probe={probe}"
)
PYGPU


bootstrap_args=(
  --model-root "$MODEL_ROOT"
  --manifest "$MODEL_MANIFEST"
  --groups "${DOWNLOAD_GROUPS:-core,starter-loras}"
)
if [ "${VERIFY_MODEL_SHA256,,}" = "true" ]; then
  bootstrap_args+=(--verify-sha256)
fi
if [ "${AUTO_DOWNLOAD_MODELS,,}" = "true" ]; then
  python -u /opt/krea/scripts/bootstrap_models.py "${bootstrap_args[@]}"
elif [ "${VERIFY_MODEL_SHA256,,}" = "true" ]; then
  python -u /opt/krea/scripts/bootstrap_models.py \
    "${bootstrap_args[@]}" \
    --verify-only
fi

if [ "${PRELOAD_FILE_CACHE,,}" = "true" ]; then
  python -u /opt/krea/scripts/preload_loras.py \
    --model-root "$MODEL_ROOT" \
    --catalog "$LORA_CATALOG" \
    --names "${PRELOAD_LORAS:-realism,darkbrush}"
fi

python - "$MODEL_ROOT" > /tmp/krea-extra-model-paths.yaml <<'PYYAML'
import sys
from pathlib import Path

model_root = str(Path(sys.argv[1]).resolve())
print("krea_storage:")
print(f"  base_path: {model_root}")
for key in (
    "diffusion_models",
    "text_encoders",
    "vae",
    "loras",
    "checkpoints",
    "clip_vision",
    "embeddings",
    "controlnet",
    "upscale_models",
):
    print(f"  {key}: {key}/")
PYYAML

COMFY_PID=""
HANDLER_PID=""
cleanup() {
  set +e
  [ -n "$HANDLER_PID" ] && kill "$HANDLER_PID" 2>/dev/null
  [ -n "$COMFY_PID" ] && kill "$COMFY_PID" 2>/dev/null
  [ -n "$HANDLER_PID" ] && wait "$HANDLER_PID" 2>/dev/null
  [ -n "$COMFY_PID" ] && wait "$COMFY_PID" 2>/dev/null
}
trap cleanup EXIT INT TERM

echo "Starting ComfyUI on ${COMFY_HOST}:${COMFY_PORT}"
python -u /comfyui/main.py \
  --disable-auto-launch \
  --disable-metadata \
  --listen "$COMFY_HOST" \
  --port "$COMFY_PORT" \
  --extra-model-paths-config /tmp/krea-extra-model-paths.yaml \
  --output-directory "$OUTPUT_ROOT" \
  --verbose "$COMFY_LOG_LEVEL" \
  --log-stdout &
COMFY_PID=$!
echo "$COMFY_PID" > /tmp/comfyui.pid

python - <<'PYWAIT'
import os
import sys
import time
import requests

url = (
    f"http://{os.environ.get('COMFY_HOST', '127.0.0.1')}:"
    f"{os.environ.get('COMFY_PORT', '8188')}/system_stats"
)
deadline = time.monotonic() + int(os.environ.get("COMFY_START_TIMEOUT", "300"))
last = "not started"
while time.monotonic() < deadline:
    try:
        pid = int(open("/tmp/comfyui.pid", encoding="utf-8").read().strip())
        os.kill(pid, 0)
    except (FileNotFoundError, ValueError, ProcessLookupError):
        print("ComfyUI process exited before becoming ready", file=sys.stderr)
        raise SystemExit(1)
    except PermissionError:
        pass
    try:
        response = requests.get(url, timeout=5)
        if response.ok:
            print("ComfyUI is ready")
            raise SystemExit(0)
        last = f"HTTP {response.status_code}"
    except Exception as exc:
        last = str(exc)
    time.sleep(0.5)
print(f"ComfyUI startup timeout: {last}", file=sys.stderr)
raise SystemExit(1)
PYWAIT

python -u /opt/krea/scripts/validate_runtime.py

if [ "${WARMUP_ON_START,,}" = "true" ]; then
  python -u /opt/krea/scripts/warmup.py
fi

echo "Starting RunPod handler"
python -u /opt/krea/src/handler.py &
HANDLER_PID=$!

set +e
wait -n "$COMFY_PID" "$HANDLER_PID"
status=$?
set -e
echo "Worker process exited with status $status" >&2
exit "$status"
