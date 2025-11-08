"""NovelAI 模型 JSON 构造函数。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional


def _build_text2image(model: str, **kwargs: Any) -> Dict[str, Any]:
    """构建基础的文本生图请求payload。"""

    positive_prompt: str = kwargs.get("prompt", "")
    negative_prompt: str = kwargs.get("negative_prompt", "")

    v4_prompt_positive: List[dict] = kwargs.get("v4_prompt_positive", [])
    v4_prompt_negative: List[dict] = kwargs.get("v4_prompt_negative", [])
    character_prompts: List[dict] = kwargs.get("character_prompts", [])

    reference_image_multiple: Optional[List[str]] = kwargs.get("reference_image_multiple")
    reference_information_extracted_multiple: Optional[List[Any]] = kwargs.get(
        "reference_information_extracted_multiple"
    )
    reference_strength_multiple: Optional[List[float]] = kwargs.get("reference_strength_multiple")

    director_reference_images: Optional[List[str]] = kwargs.get("director_reference_images")
    director_reference_descriptions: Optional[List[dict]] = kwargs.get("director_reference_descriptions")
    director_reference_information_extracted: Optional[List[Any]] = kwargs.get(
        "director_reference_information_extracted"
    )
    director_reference_strength_values: Optional[List[float]] = kwargs.get("director_reference_strength_values")
    director_reference_secondary_strength_values: Optional[List[float]] = kwargs.get(
        "director_reference_secondary_strength_values"
    )

    parameters: Dict[str, Any] = {
        "params_version": kwargs.get("params_version", 3),
        "width": kwargs.get("width", 832),
        "height": kwargs.get("height", 1216),
        "scale": kwargs.get("scale", 5),
        "sampler": kwargs.get("sampler", "k_euler_ancestral"),
        "steps": kwargs.get("steps", 28),
        "n_samples": kwargs.get("n_samples", 1),
        "ucPreset": kwargs.get("uc_preset", 0),
        "qualityToggle": kwargs.get("quality_toggle", False),
        "autoSmea": kwargs.get("auto_smea", False),
        "dynamic_thresholding": kwargs.get("dynamic_thresholding", False),
        "controlnet_strength": kwargs.get("controlnet_strength", 1),
        "legacy": kwargs.get("legacy", False),
        "add_original_image": kwargs.get("add_original_image", True),
        "cfg_rescale": kwargs.get("cfg_rescale", 0.0),
        "noise_schedule": kwargs.get("noise_schedule", "native"),
        "legacy_v3_extend": kwargs.get("legacy_v3_extend", False),
        "skip_cfg_above_sigma": kwargs.get("skip_cfg_above_sigma"),
        "use_coords": kwargs.get("use_coords", True),
        "normalize_reference_strength_multiple": kwargs.get(
            "normalize_reference_strength_multiple", False
        ),
        "use_order": kwargs.get("use_order", True),
        "legacy_uc": kwargs.get("legacy_uc", False),
        "seed": kwargs.get("seed", 0),
        "characterPrompts": character_prompts,
        "negative_prompt": negative_prompt,
        "sm": kwargs.get("sm", False),
        "sm_dyn": kwargs.get("sm_dyn", False),
        "v4_prompt": {
            "caption": {
                "base_caption": positive_prompt,
                "char_captions": v4_prompt_positive,
            },
            "use_coords": kwargs.get("use_coords", True),
            "use_order": kwargs.get("use_order", True),
        },
        "v4_negative_prompt": {
            "caption": {
                "base_caption": negative_prompt,
                "char_captions": v4_prompt_negative,
            },
            "legacy_uc": kwargs.get("legacy_uc", False),
        },
        "stream": kwargs.get("stream", "msgpack"),
    }

    if kwargs.get("sampler") == "k_euler_ancestral":
        parameters["deliberate_euler_ancestral_bug"] = kwargs.get("deliberate_euler_ancestral_bug", False)
        parameters["prefer_brownian"] = kwargs.get("prefer_brownian", True)

    if reference_image_multiple:
        parameters["reference_image_multiple"] = reference_image_multiple
    if reference_information_extracted_multiple:
        parameters["reference_information_extracted_multiple"] = reference_information_extracted_multiple
    if reference_strength_multiple:
        parameters["reference_strength_multiple"] = reference_strength_multiple

    if director_reference_images:
        parameters["director_reference_images"] = director_reference_images
    if director_reference_descriptions:
        parameters["director_reference_descriptions"] = director_reference_descriptions
    if director_reference_information_extracted:
        parameters["director_reference_information_extracted"] = director_reference_information_extracted
    if director_reference_strength_values:
        parameters["director_reference_strength_values"] = director_reference_strength_values
    if director_reference_secondary_strength_values:
        parameters["director_reference_secondary_strength_values"] = director_reference_secondary_strength_values

    # 清理可能为None的字段
    for key in ["skip_cfg_above_sigma"]:
        if parameters.get(key) is None:
            parameters.pop(key, None)

    payload: Dict[str, Any] = {
        "input": positive_prompt,
        "model": model,
        "action": "generate",
        "parameters": parameters,
        "use_new_shared_trial": kwargs.get("use_new_shared_trial", True),
    }

    return payload


def _build_image2image(payload: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
    """基于文本生图payload构建图生图payload。"""

    new_payload = deepcopy(payload)
    new_payload["action"] = "img2img"

    params = new_payload.setdefault("parameters", {})
    params.update(
        {
            "strength": kwargs.get("strength", 0.7),
            "noise": kwargs.get("noise", 0.0),
            "image": kwargs.get("image"),
            "extra_noise_seed": kwargs.get("extra_noise_seed", kwargs.get("seed", params.get("seed", 0))),
            "color_correct": kwargs.get("color_correct", False),
        },
    )

    for required in ["image"]:
        if params.get(required) is None:
            raise ValueError(f"image2image payload requires '{required}'")

    return new_payload


def _build_inpaint(payload: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
    """基于图生图payload构建局部重绘payload。"""

    new_payload = _build_image2image(payload, **kwargs)
    model = payload.get("model", "")
    if model.endswith("-curated"):
        new_payload["model"] = f"{model}-inpainting"
    params = new_payload.setdefault("parameters", {})
    params["mask"] = kwargs.get("mask")
    params["add_original_image"] = kwargs.get("add_original_image", False)

    if params.get("mask") is None:
        raise ValueError("inpaint payload requires 'mask'")

    return new_payload


def build_nai45f_text2image(**kwargs: Any) -> Dict[str, Any]:
    return _build_text2image("nai-diffusion-4-5-full", **kwargs)


def build_nai45c_text2image(**kwargs: Any) -> Dict[str, Any]:
    return _build_text2image("nai-diffusion-4-5-curated", **kwargs)


def build_nai4f_text2image(**kwargs: Any) -> Dict[str, Any]:
    return _build_text2image("nai-diffusion-4-full", **kwargs)


def build_nai4cp_text2image(**kwargs: Any) -> Dict[str, Any]:
    return _build_text2image("nai-diffusion-4-curated-preview", **kwargs)


def build_nai3_text2image(**kwargs: Any) -> Dict[str, Any]:
    return _build_text2image("nai-diffusion-3", **kwargs)


def build_naif3_text2image(**kwargs: Any) -> Dict[str, Any]:
    return _build_text2image("nai-diffusion-furry-3", **kwargs)


def build_image2image(payload: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
    return _build_image2image(payload, **kwargs)


def build_inpaint(payload: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
    return _build_inpaint(payload, **kwargs)
