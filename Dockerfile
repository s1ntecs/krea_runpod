ARG BASE_IMAGE=runpod/worker-comfyui:5.10.0-base
FROM ${BASE_IMAGE}

USER root
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/opt/krea/src \
    HF_HUB_DISABLE_TELEMETRY=1 \
    MODEL_ROOT=/runpod-volume/models \
    OUTPUT_ROOT=/tmp/krea-comfy-output \
    COMFY_HOST=127.0.0.1 \
    COMFY_PORT=8188

WORKDIR /opt/krea
COPY requirements-worker.txt ./
RUN uv pip install --no-cache -r requirements-worker.txt

COPY config ./config
COPY src ./src
COPY scripts ./scripts

RUN chmod +x src/start.sh scripts/*.py scripts/*.sh \
    && python -m compileall -q src scripts \
    && bash -n src/start.sh \
    && bash -n scripts/s3_upload.sh

CMD ["/opt/krea/src/start.sh"]
