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


def build_edit_workflow(
    request: GenerationRequest,
    loras: list[ResolvedLora],
    settings: Settings,
    filename_prefix: str,
    image_names: list[str],
    edit_lora_name: str,
) -> WorkflowResult:
    """Builds the Krea 2 Identity Edit graph.

    Mirrors workflows/krea2_identity_edit.json from comfyui-krea2edit: the edit
    LoRA sits directly on the UNet, both conditionings go through the grounded
    encoder, and ModelSamplingAuraFlow is deliberately absent.
    """
    if not image_names:
        raise ValueError("edit workflow needs at least one uploaded reference image")

    final_prompt = append_lora_triggers(request.prompt, loras)
    workflow: dict[str, dict] = {
        "unet": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": settings.unet_name, "weight_dtype": "default"},
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
        "latent": {
            "class_type": "EmptySD3LatentImage",
            "inputs": {
                "width": request.width,
                "height": request.height,
                "batch_size": request.batch_size,
            },
        },
    }

    for index, name in enumerate(image_names):
        workflow[f"src_{index:02d}"] = {
            "class_type": "LoadImage",
            "inputs": {"image": name},
        }
        workflow[f"src_lat_{index:02d}"] = {
            "class_type": "VAEEncode",
            "inputs": {"pixels": [f"src_{index:02d}", 0], "vae": ["vae", 0]},
        }

    # The identity-edit LoRA is what makes editing work at all, so it is applied
    # first; user-selected LoRAs stack on top and steer the prior.
    workflow["lora_edit"] = {
        "class_type": "LoraLoaderModelOnly",
        "inputs": {
            "model": ["unet", 0],
            "lora_name": edit_lora_name,
            "strength_model": 1.0,
        },
    }
    model_node = "lora_edit"
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

    patch_inputs: dict = {
        "model": [model_node, 0],
        "source_latent": ["src_lat_00", 0],
        "vae": ["vae", 0],
        "source_image": ["src_00", 0],
        "target_latent": ["latent", 0],
        "ref_boost": request.ref_boost,
        "ref_boost_a": request.ref_boost_a,
        "fit_mode": "fit",
    }
    encode_extra: dict = {}
    if len(image_names) > 1:
        patch_inputs["source_latent_b"] = ["src_lat_01", 0]
        patch_inputs["source_image_b"] = ["src_01", 0]
        encode_extra["image_b"] = ["src_01", 0]

    workflow["edit_patch"] = {
        "class_type": "Krea2EditModelPatch",
        "inputs": patch_inputs,
    }
    workflow["positive"] = {
        "class_type": "Krea2EditGroundedEncode",
        "inputs": {
            "clip": ["clip", 0],
            "prompt": final_prompt,
            "image": ["src_00", 0],
            "grounding_px": request.grounding_px,
            **encode_extra,
        },
    }
    workflow["negative"] = {
        "class_type": "Krea2EditGroundedEncode",
        "inputs": {
            "clip": ["clip", 0],
            "prompt": "",
            "image": ["src_00", 0],
            "grounding_px": request.grounding_px,
            **encode_extra,
        },
    }
    workflow["sampler"] = {
        "class_type": "KSampler",
        "inputs": {
            "model": ["edit_patch", 0],
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
