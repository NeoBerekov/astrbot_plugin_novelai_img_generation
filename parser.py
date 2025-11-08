"""处理 /nai图片生成 指令的参数解析。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .constants import CHARACTER_POSITIONS, RESOLUTION_MAP, SAMPLERS


class ParseError(Exception):
    """指令解析错误。"""


@dataclass
class CharacterPrompt:
    index: int
    positive: str
    negative: Optional[str] = None
    position: str = "C3"


@dataclass
class ParsedParams:
    positive_prompt: str
    negative_prompt: Optional[str]
    negative_preset: str
    model_name: Optional[str]
    furry_mode: bool
    add_quality_tags: bool
    base_image: Optional[str]
    base_strength: float
    base_noise: float
    width: int
    height: int
    steps: int
    guidance: float
    cfg_rescale: float
    seed: Optional[int]
    sampler: str
    use_character_zones: bool
    characters: List[CharacterPrompt] = field(default_factory=list)
    character_reference: Optional[str] = None
    character_reference_strength: float = 1.0
    style_aware: bool = False
    raw_params: Dict[str, str] = field(default_factory=dict)


_PAIR_PATTERN = re.compile(r"\s*(\S+)[：:]\s*<(.*?)>(?=\s*\S+[：:]\s*<|\s*$)", re.S)
_GENERAL_KEYS = {
    "正面词条",
    "负面词条",
    "是否有福瑞",
    "添加质量词",
    "底图",
    "底图重绘强度",
    "底图加噪强度",
    "分辨率",
    "步数",
    "指导系数",
    "重采样系数",
    "种子",
    "采样器",
    "角色是否分区",
    "角色参考",
    "角色参考强度",
    "是否注意原画风",
    "模型",
}


def _parse_bool(value: Optional[str], field: str, default: bool = False) -> bool:
    if value is None:
        return default
    text = value.strip()
    if text in {"是", "true", "True", "1", "yes", "YES"}:
        return True
    if text in {"否", "false", "False", "0", "no", "NO"}:
        return False
    raise ParseError(f"{field}参数无效，只能填写'是'或'否'")


def _parse_float(
    value: Optional[str],
    field: str,
    default: float,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
) -> float:
    if value is None or value.strip() == "":
        return default
    try:
        number = float(value.strip())
    except ValueError as exc:
        raise ParseError(f"{field}参数必须是数字") from exc

    if min_value is not None and number < min_value:
        raise ParseError(f"{field}参数不能小于{min_value}")
    if max_value is not None and number > max_value:
        raise ParseError(f"{field}参数不能大于{max_value}")
    return number


def _parse_int(
    value: Optional[str],
    field: str,
    default: Optional[int] = None,
    min_value: Optional[int] = None,
    max_value: Optional[int] = None,
) -> Optional[int]:
    if value is None or value.strip() == "":
        return default
    try:
        number = int(value.strip())
    except ValueError as exc:
        raise ParseError(f"{field}参数必须是整数") from exc

    if min_value is not None and number < min_value:
        raise ParseError(f"{field}参数不能小于{min_value}")
    if max_value is not None and number > max_value:
        raise ParseError(f"{field}参数不能大于{max_value}")
    return number


def _collect_pairs(message: str) -> List[Tuple[str, str]]:
    pairs = []
    for match in _PAIR_PATTERN.finditer(message):
        key = match.group(1).strip()
        value = match.group(2).strip()
        pairs.append((key, value))
    return pairs


def parse_generation_message(message: str) -> ParsedParams:
    if not message:
        raise ParseError("指令格式错误，缺少/nai开头")

    # 统一替换中文逗号为英文逗号，避免参数分隔问题
    message = message.replace("，", ",")

    stripped = message.strip()
    if not (stripped == "/nai" or stripped.startswith("/nai")):
        raise ParseError("指令格式错误，缺少/nai开头")

    content = stripped[len("/nai"):].strip()
    if not content:
        raise ParseError("未填写提示词")

    pairs = _collect_pairs(content)
    if not pairs:
        raise ParseError("参数格式错误，请使用 Key:<Value> 格式")

    general_params: Dict[str, str] = {}
    character_params: Dict[int, Dict[str, str]] = {}

    def _set_character_param(key: str, value: str) -> bool:
        if not key.startswith("角色"):
            return False

        suffixes = ["正面词条", "负面词条", "位置"]
        matched_suffix = next((suffix for suffix in suffixes if key.endswith(suffix)), None)
        if matched_suffix is None:
            return False

        index_part = key[len("角色") : -len(matched_suffix)]
        if not index_part.isdigit():
            raise ParseError(f"角色参数格式错误: {key}")
        index = int(index_part)
        if not 1 <= index <= 5:
            raise ParseError("角色序号仅支持1-5")

        entry = character_params.setdefault(index, {})
        if matched_suffix == "正面词条":
            entry["positive"] = value
        elif matched_suffix == "负面词条":
            entry["negative"] = value
        elif matched_suffix == "位置":
            entry["position"] = value
        return True

    for key, value in pairs:
        if _set_character_param(key, value):
            continue
        if key not in _GENERAL_KEYS:
            raise ParseError(f"未知参数: {key}")
        general_params[key] = value

    positive_prompt = general_params.get("正面词条")
    if not positive_prompt:
        raise ParseError("未填写提示词")

    model_name = general_params.get("模型") or None

    negative_prompt = general_params.get("负面词条") or None
    negative_preset = "Heavy"

    furry_mode = _parse_bool(general_params.get("是否有福瑞"), "是否有福瑞", default=False)
    add_quality = _parse_bool(general_params.get("添加质量词"), "添加质量词", default=False)

    base_image = general_params.get("底图") or None
    base_strength = _parse_float(
        general_params.get("底图重绘强度"),
        "底图重绘强度",
        default=0.7,
        min_value=0.0,
        max_value=1.0,
    )
    base_noise = _parse_float(
        general_params.get("底图加噪强度"),
        "底图加噪强度",
        default=0.0,
        min_value=0.0,
        max_value=0.99,
    )

    resolution_key = general_params.get("分辨率", "竖图")
    if resolution_key not in RESOLUTION_MAP:
        raise ParseError("分辨率参数无效")
    width, height = RESOLUTION_MAP[resolution_key]

    steps = _parse_int(general_params.get("步数"), "步数", default=28, min_value=1, max_value=28) or 28
    guidance = _parse_float(
        general_params.get("指导系数"), "指导系数", default=5.0, min_value=0.0, max_value=10.0
    )
    cfg_rescale = _parse_float(
        general_params.get("重采样系数"), "重采样系数", default=0.0, min_value=0.0, max_value=1.0
    )
    seed = _parse_int(general_params.get("种子"), "种子", default=None)

    sampler = general_params.get("采样器", "k_euler_ancestral")
    if sampler not in SAMPLERS:
        raise ParseError("采样器参数无效")

    use_character_zones = _parse_bool(
        general_params.get("角色是否分区"), "角色是否分区", default=False
    )

    if len(character_params) > 5:
        raise ParseError("角色数量最多支持5个")

    characters: List[CharacterPrompt] = []
    for index, data in sorted(character_params.items()):
        positive = data.get("positive")
        if not positive:
            raise ParseError(f"角色{index}缺少正面词条")
        position = (data.get("position") or "C3").upper()
        if position not in CHARACTER_POSITIONS:
            raise ParseError(f"角色{index}位置参数无效")
        characters.append(
            CharacterPrompt(
                index=index,
                positive=positive,
                negative=data.get("negative"),
                position=position,
            ),
        )

    if len(characters) <= 1:
        use_character_zones = False

    character_reference = general_params.get("角色参考") or None
    if character_reference and base_image:
        character_reference = None  # 底图已存在则忽略角色参考

    character_reference_strength = _parse_float(
        general_params.get("角色参考强度"),
        "角色参考强度",
        default=1.0,
        min_value=0.0,
        max_value=1.0,
    )

    style_aware = _parse_bool(general_params.get("是否注意原画风"), "是否注意原画风", default=False)

    return ParsedParams(
        positive_prompt=positive_prompt,
        negative_prompt=negative_prompt,
        negative_preset=negative_preset,
        model_name=model_name,
        furry_mode=furry_mode,
        add_quality_tags=add_quality,
        base_image=base_image,
        base_strength=base_strength,
        base_noise=base_noise,
        width=width,
        height=height,
        steps=steps,
        guidance=guidance,
        cfg_rescale=cfg_rescale,
        seed=seed,
        sampler=sampler,
        use_character_zones=use_character_zones,
        characters=characters,
        character_reference=character_reference,
        character_reference_strength=character_reference_strength,
        style_aware=style_aware,
        raw_params=general_params,
    )
