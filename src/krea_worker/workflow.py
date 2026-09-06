from __future__ import annotations

from dataclasses import dataclass

from .lora_registry import ResolvedLora
from .request import GenerationRequest
from .settings import Settings


@dataclass(frozen=True)
class WorkflowResult:
    workflow: dict
    output_node_id: str
    final_prompt: str


def append_lora_triggers(prompt: str, loras: list[ResolvedLora]) -> str:
    additions: list[str] = []
    prompt_lower = prompt.lower()
    for lora in loras:
        trigger = lora.trigger.strip()
        if lora.append_trigger and trigger and trigger.lower() not in prompt_lower:
            additions.append(trigger)
            prompt_lower += " " + trigger.lower()
    if not additions:
        return prompt
    separator = ", " if not prompt.rstrip().endswith(('.', ',', ';', ':')) else " "
    return prompt.rstrip() + separator + ", ".join(additions)


def build_workflow(
    request: GenerationRequest,
    loras: list[ResolvedLora],
    settings: Settings,
    filename_prefix: str,
) -> WorkflowResult:
    final_prompt = append_lora_triggers(request.prompt, loras)
    workflow: dict[str, dict] = {
        "unet": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": settings.unet_name,
                "weight_dtype": "default",
            },
        },
        "clip": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": settings.text_encoder_name,
                "type": "krea2",
                "device": "default",
            },
        },
        "vae": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": settings.vae_name},
        },
        "positive": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": final_prompt, "clip": ["clip", 0]},
        },
        "latent": {
            "class_type": "EmptySD3LatentImage",
            "inputs": {
                "width": request.width,
                "height": request.height,
                "batch_size": request.batch_size,
            },
        },
    }

    if request.negative_prompt:
        workflow["negative"] = {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": request.negative_prompt, "clip": ["clip", 0]},
        }
    else:
        workflow["negative"] = {
            "class_type": "ConditioningZeroOut",
            "inputs": {"conditioning": ["positive", 0]},
        }

    model_node = "unet"
    for index, lora in enumerate(loras, start=1):
        node_id = f"lora_{index:02d}"
        workflow[node_id] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": [model_node, 0],
                "lora_name": lora.file,
                "strength_model": lora.strength,
            },
        }
        model_node = node_id

    workflow["model_sampling"] = {
        "class_type": "ModelSamplingAuraFlow",
        "inputs": {"model": [model_node, 0], "shift": settings.model_shift},
    }
    workflow["sampler"] = {
        "class_type": "KSampler",
        "inputs": {
            "model": ["model_sampling", 0],
            "seed": request.seed,
            "steps": request.steps,
            "cfg": request.cfg,
            "sampler_name": request.sampler_name,
            "scheduler": request.scheduler,
            "denoise": 1.0,
            "positive": ["positive", 0],
            "negative": ["negative", 0],
            "latent_image": ["latent", 0],
        },
    }
    workflow["decode"] = {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["sampler", 0], "vae": ["vae", 0]},
    }
    workflow["save"] = {
        "class_type": "SaveImage",
        "inputs": {"images": ["decode", 0], "filename_prefix": filename_prefix},
    }
    return WorkflowResult(workflow=workflow, output_node_id="save", final_prompt=final_prompt)
