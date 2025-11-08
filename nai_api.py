"""NovelAI API 调用逻辑。"""

from __future__ import annotations

import random
from typing import Optional, Tuple

import aiohttp

from .constants import (
    get_negative_preset,
    get_quality_tags,
    get_skip_cfg_above_sigma,
    get_uc_preset_value,
    position_to_float,
)
from .image_utils import extract_zip_image
from .nai_models import (
    build_image2image,
    build_inpaint,
    build_nai3_text2image,
    build_nai45c_text2image,
    build_nai45f_text2image,
    build_nai4cp_text2image,
    build_nai4f_text2image,
    build_naif3_text2image,
)
from .parser import CharacterPrompt, ParsedParams


class NovelAIAPIError(Exception):
    """NovelAI接口调用失败。"""


_MODEL_BUILDERS = {
    "nai-diffusion-4-5-full": build_nai45f_text2image,
    "nai-diffusion-4-5-curated": build_nai45c_text2image,
    "nai-diffusion-4-full": build_nai4f_text2image,
    "nai-diffusion-4-curated-preview": build_nai4cp_text2image,
    "nai-diffusion-3": build_nai3_text2image,
    "nai-diffusion-furry-3": build_naif3_text2image,
}


class NovelAIAPI:
    API_URL = "https://image.novelai.net/ai/generate-image"

    def __init__(self, token: str, proxy: Optional[str] = None) -> None:
        if not token:
            raise NovelAIAPIError("未配置NovelAI Token")
        self.token = token
        self.proxy = proxy
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=180)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    def build_payload(
        self,
        parsed: ParsedParams,
        *,
        model: str,
        base_image: Optional[str] = None,
        mask_image: Optional[str] = None,
        character_reference: Optional[str] = None,
    ) -> Tuple[dict, int]:
        builder = _MODEL_BUILDERS.get(model)
        if not builder:
            raise NovelAIAPIError(f"不支持的模型: {model}")

        seed = parsed.seed if parsed.seed is not None else random.randint(1_000_000_000, 9_999_999_999)

        prompt = parsed.positive_prompt.strip()
        if parsed.furry_mode:
            prompt = f"fur dataset, {prompt}"

        quality_tags = get_quality_tags(model)
        if parsed.add_quality_tags and quality_tags:
            prompt = f"{prompt}{quality_tags}"

        negative_prompt = parsed.negative_prompt or get_negative_preset(model, parsed.negative_preset)
        uc_preset_value = get_uc_preset_value(model, parsed.negative_preset)
        skip_sigma = get_skip_cfg_above_sigma(model)

        characters_exist = bool(parsed.characters)
        use_zones = parsed.use_character_zones and characters_exist
        extra_positive_parts = []
        extra_negative_parts = []
        v4_positive = []
        v4_negative = []
        character_prompts = []
        if use_zones:
            for char in parsed.characters:
                center = _character_center(char)
                v4_positive.append({"char_caption": char.positive, "centers": [center]})
                v4_negative.append({"char_caption": char.negative or "", "centers": [center]})
                character_prompts.append(
                    {
                        "prompt": char.positive,
                        "uc": char.negative or "",
                        "center": center,
                        "enabled": True,
                    },
                )
        elif characters_exist:
            for char in parsed.characters:
                if char.positive:
                    extra_positive_parts.append(char.positive)
                if char.negative:
                    extra_negative_parts.append(char.negative)

        if extra_positive_parts:
            addon = ", ".join(extra_positive_parts)
            prompt = f"{prompt}, {addon}" if prompt else addon
        if extra_negative_parts:
            addon = ", ".join(extra_negative_parts)
            negative_prompt = f"{negative_prompt}, {addon}" if negative_prompt else addon

        payload = builder(
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=parsed.width,
            height=parsed.height,
            scale=parsed.guidance,
            sampler=parsed.sampler,
            steps=parsed.steps,
            uc_preset=uc_preset_value,
            quality_toggle=parsed.add_quality_tags,
            auto_smea=False,
            dynamic_thresholding=False,
            controlnet_strength=1,
            legacy=False,
            add_original_image=True,
            cfg_rescale=parsed.cfg_rescale,
            noise_schedule="native",
            legacy_v3_extend=False,
            skip_cfg_above_sigma=skip_sigma,
            use_coords=use_zones,
            normalize_reference_strength_multiple=False,
            use_order=True,
            legacy_uc=False,
            seed=seed,
            character_prompts=character_prompts,
            v4_prompt_positive=v4_positive,
            v4_prompt_negative=v4_negative,
            sm=False,
            sm_dyn=False,
            use_new_shared_trial=True,
        )

        params = payload["parameters"]
        params["cfg_rescale"] = parsed.cfg_rescale
        params["seed"] = seed

        if character_reference:
            params["director_reference_images"] = [character_reference]
            params["director_reference_descriptions"] = [
                {
                    "caption": {
                        "base_caption": "character&style" if parsed.style_aware else "character",
                        "char_captions": [],
                    },
                    "legacy_uc": False,
                }
            ]
            params["director_reference_information_extracted"] = [1]
            params["director_reference_strength_values"] = [parsed.character_reference_strength]
            params["director_reference_secondary_strength_values"] = [
                max(0.0, 1.0 - parsed.character_reference_strength)
            ]

        if base_image:
            payload = build_image2image(
                payload,
                image=base_image,
                strength=parsed.base_strength,
                noise=parsed.base_noise,
                extra_noise_seed=seed,
                color_correct=False,
            )

        if mask_image:
            payload = build_inpaint(
                payload,
                mask=mask_image,
                strength=parsed.base_strength,
                noise=parsed.base_noise,
                extra_noise_seed=seed,
                color_correct=False,
            )

        return payload, seed

    async def generate_image(self, payload: dict) -> bytes:
        session = await self._get_session()
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Referer": "https://novelai.net/",
            "Origin": "https://novelai.net",
        }

        try:
            async with session.post(
                self.API_URL,
                json=payload,
                headers=headers,
                proxy=self.proxy,
            ) as response:
                if response.status != 200:
                    text = await response.text()
                    raise NovelAIAPIError(f"NovelAI返回错误({response.status}): {text}")
                data = await response.read()
        except aiohttp.ClientError as exc:
            raise NovelAIAPIError(f"NovelAI请求失败: {exc}") from exc

        try:
            return extract_zip_image(data)
        except Exception as exc:  # noqa: BLE001
            raise NovelAIAPIError(f"解析NovelAI响应失败: {exc}") from exc


def _character_center(character: CharacterPrompt) -> dict:
    x, y = position_to_float(character.position)
    return {"x": x, "y": y}
