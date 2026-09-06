# syntax=docker/dockerfile:1
ARG BASE_IMAGE=runpod/worker-comfyui:5.10.0-base
FROM ${BASE_IMAGE}

USER root
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/opt/krea/src \
    HF_HUB_DISABLE_TELEMETRY=1 \
    HF_HUB_DISABLE_XET=1 \
    HF_HUB_ENABLE_HF_TRANSFER=0 \
    HF_XET_HIGH_PERFORMANCE=0 \
    OUTPUT_ROOT=/tmp/krea-comfy-output \
    COMFY_HOST=127.0.0.1 \
    COMFY_PORT=8188

# Where the worker looks for weights.
# Volume build (default): weights live on the RunPod Network Volume.
# Baked build: pass --build-arg MODEL_ROOT_DEFAULT=/opt/krea/models so the
# endpoint needs no volume and is therefore not pinned to one datacenter.
ARG MODEL_ROOT_DEFAULT=/runpod-volume/models
ENV MODEL_ROOT=${MODEL_ROOT_DEFAULT}

WORKDIR /opt/krea
COPY requirements-worker.txt ./
RUN uv pip install --no-cache -r requirements-worker.txt

COPY config ./config
COPY scripts ./scripts

# Optional weight baking. Empty (default) keeps the volume-based image.
# Kept ahead of `COPY src` so editing worker code never re-downloads weights.
ARG BAKE_MODEL_GROUPS=
RUN --mount=type=secret,id=hf_token \
    if [ -n "${BAKE_MODEL_GROUPS}" ]; then \
      HF_TOKEN="$(cat /run/secrets/hf_token 2>/dev/null || true)" \
      python scripts/bootstrap_models.py \
        --model-root "${MODEL_ROOT}" \
        --manifest config/models.json \
        --groups "${BAKE_MODEL_GROUPS}"; \
    fi

COPY src ./src

RUN chmod +x src/start.sh scripts/*.py scripts/*.sh \
    && python -m compileall -q src scripts \
    && bash -n src/start.sh \
    && bash -n scripts/s3_upload.sh

CMD ["/opt/krea/src/start.sh"]
