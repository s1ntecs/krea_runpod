#!/usr/bin/env bash
set -Eeuo pipefail

if [ "$#" -ne 2 ]; then
  echo "Usage: $0 LOCAL_FILE REMOTE_PATH" >&2
  exit 2
fi

: "${RUNPOD_VOLUME_ID:?Set RUNPOD_VOLUME_ID}"
: "${RUNPOD_S3_ENDPOINT:?Set RUNPOD_S3_ENDPOINT, for example https://s3api-eu-ro-1.runpod.io/}"
: "${RUNPOD_S3_REGION:?Set RUNPOD_S3_REGION, for example EU-RO-1}"
: "${AWS_ACCESS_KEY_ID:?Set AWS_ACCESS_KEY_ID}"
: "${AWS_SECRET_ACCESS_KEY:?Set AWS_SECRET_ACCESS_KEY}"

local_file="$1"
remote_path="${2#/}"

if [ ! -f "$local_file" ]; then
  echo "Local file not found: $local_file" >&2
  exit 1
fi

aws s3 cp \
  "$local_file" \
  "s3://${RUNPOD_VOLUME_ID}/${remote_path}" \
  --endpoint-url "$RUNPOD_S3_ENDPOINT" \
  --region "$RUNPOD_S3_REGION" \
  --no-progress
