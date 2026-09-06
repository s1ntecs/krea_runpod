#!/usr/bin/env bash
set -Eeuo pipefail

: "${RUNPOD_API_KEY:?Set RUNPOD_API_KEY}"
: "${RUNPOD_ENDPOINT_ID:?Set RUNPOD_ENDPOINT_ID}"

request_file="${1:-examples/request-realism.json}"
curl -sS -X POST \
  -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
  -H "Content-Type: application/json" \
  "https://api.runpod.ai/v2/${RUNPOD_ENDPOINT_ID}/runsync" \
  -d "@${request_file}"
