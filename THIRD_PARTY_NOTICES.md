# Third-party notices and model licenses

This repository's original worker code is licensed under MIT. That license does not replace the licenses of the container base image, ComfyUI, PyTorch, RunPod SDK, Krea 2 weights, text encoder, VAE, or LoRAs.

## Container base

The Dockerfile extends `runpod/worker-comfyui:5.10.0-base`. Review the upstream repository and image licenses before distributing a derived image:

- https://github.com/runpod-workers/worker-comfyui
- https://github.com/Comfy-Org/ComfyUI

## Krea 2 model files

The manifest downloads Krea 2-related weights under the Krea 2 Community License:

- https://huggingface.co/Comfy-Org/Krea-2
- https://www.krea.ai/krea-2-licensing

Do not treat the repository's MIT license as permission to use model weights outside their own license terms.

## Starter LoRAs

- Realism: https://huggingface.co/gokaygokay/Krea-2-Realism-LoRA
- Darkbrush: https://huggingface.co/Comfy-Org/Krea-2/blob/main/loras/krea2_darkbrush.safetensors
- Optional retroanime: https://huggingface.co/Comfy-Org/Krea-2/blob/main/loras/krea2_retroanime.safetensors

Each LoRA keeps its upstream license and attribution requirements.

## User-provided LoRAs

The worker can discover arbitrary `.safetensors` files from Network Volume. The operator is responsible for verifying the license, training-data restrictions, consent requirements, commercial-use terms, and applicable law for every uploaded LoRA.
