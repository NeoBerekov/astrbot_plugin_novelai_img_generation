"""NovelAI 图片生成插件主入口。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import importlib
import json
import re

yaml = None
try:
    yaml = importlib.import_module("yaml")
except ImportError:  # pragma: no cover - 运行时检测
    pass

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import At, Image, Plain
from astrbot.api.star import Context, Star, register
from astrbot.core.message.message_event_result import MessageChain

from .access_control import AccessControl
from .constants import MODELS
from .image_utils import image_to_base64, save_image_from_bytes
from .llm_client import LLMError, OpenRouterLLMClient
from .nai_api import NovelAIAPI, NovelAIAPIError
from .nl_processor import NLProcessingError, NLProcessor
from .parser import ParseError, ParsedParams, parse_generation_message
from .queue_manager import RequestQueue

DEFAULT_CONFIG_TEMPLATE = """# NovelAI 插件配置模板\n\n# NovelAI API访问Token，登陆NovelAI后抓取。\nai_token: ""\n\n# HTTP代理，可选。如需走代理，填写例如 http://127.0.0.1:7890\nproxy: ""\n\n# 默认模型，可选值：\n# - nai-diffusion-4-5-full\n# - nai-diffusion-4-5-curated\n# - nai-diffusion-4-full\n# - nai-diffusion-4-curated-preview\n# - nai-diffusion-3\n# - nai-diffusion-furry-3\ndefault_model: "nai-diffusion-4-5-curated"\n\n# 图像保存路径，使用绝对路径\nimage_save_path: "{image_save_path}"\n\n# 负面词条预设（未填写"负面词条"时使用）\npreset_uc: "{preset_uc}"\n\n# 质量词，未检测到 best quality 与 masterpiece 时自动追加\nquality_words: "{quality_words}"\n\n# 默认每日调用次数上限（白名单用户可单独配置）。\ndefault_daily_limit: 10\n\n# 管理员QQ号列表，可在运行时通过命令动态调整。\nadmin_qq_list: []\n\n# 自然语言处理设置（/nainl 功能）\nnl_settings:\n  # 质量词覆盖（为空则使用全局 quality_words）\n  quality_words_override: ""\n  # 负面词条覆盖（为空则使用全局 preset_uc）\n  negative_preset_override: ""\n  # LLM 提供商，目前支持 openrouter\n  llm_provider: "openrouter"\n  # OpenRouter API 配置\n  openrouter:\n    # API Key（必填，从 https://openrouter.ai 获取）\n    api_key: ""\n    # 使用的模型列表（按优先级排序，会依次尝试直到成功）\n    # 支持的模型格式：provider/model-name，例如：\n    # - "openai/gpt-4o-mini"（推荐，性价比高）\n    # - "openai/gpt-4o"\n    # - "anthropic/claude-3-haiku"\n    # - "anthropic/claude-3.5-sonnet"\n    # - "google/gemini-pro"\n    # 更多模型请访问：https://openrouter.ai/models\n    models:\n      - "openai/gpt-4o-mini"\n      - "anthropic/claude-3-haiku"\n    # API 超时时间（秒）\n    timeout: 30\n    # HTTP-Referer（可选，用于在 openrouter.ai 上进行排名）\n    # 建议填写你的网站或项目 URL\n    http_referer: ""\n    # X-Title（可选，用于在 openrouter.ai 上进行排名）\n    # 建议填写你的项目名称\n    x_title: ""\n  # 提示词模板\n  prompt_templates:\n    # 判断描述详细度的提示词\n    detail_check: |\n      你是一个专业的图像生成提示词评估助手。请使用思维链的方式，逐步分析用户描述是否足够详细。\n      \n      分析步骤：\n      \n      第一步：分析主体是否明确\n      - 思考：描述中是否明确指出了图像的主要对象？（如：人物、动物、物体、场景等）\n      - 思考：主体的特征是否足够具体？（如：人物的外貌、物体的形状、场景的类型等）\n      - 结论：如果主体清晰且特征具体，则主体明确；否则主体不明确。\n      \n      第二步：分析细节是否足够\n      - 思考：描述中是否包含了足够的视觉细节？（如：服装、表情、动作、姿态、纹理、材质、装饰等）\n      - 思考：这些细节是否能够帮助生成清晰的图像？\n      - 结论：如果细节丰富且有助于图像生成，则细节足够；否则细节不足。\n      \n      第三步：分析背景是否明确\n      - 思考：描述中是否明确提及了背景环境？（如：室内、室外、具体场景、抽象背景等）\n      - 思考：背景的描述是否足够具体？（如：房间类型、自然环境、城市景观等）\n      - 结论：如果背景描述清晰具体，则背景明确；否则背景不明确。\n      \n      第四步：分析构图是否明确\n      - 思考：描述中是否包含了构图相关信息？（如：全身、半身、特写、远景、中景、近景等）\n      - 思考：是否包含了视角或镜头角度信息？（如：正面、侧面、背面、仰视、俯视、平视等）\n      - 结论：如果构图信息清晰，则构图明确；否则构图不明确。\n      \n      综合判断：\n      - 回顾以上四个步骤的分析结果\n      - 如果主体明确、细节足够、背景明确、构图明确，则整体判断为"详细"\n      - 如果以上任意一个方面不够明确或不足，则整体判断为"不详细"\n      \n      用户描述：{user_input}\n      \n      请在内部完成全部推理，不要向用户展示任何思考过程。最后只回复"详细"或"不详细"，不要添加任何其他文字、解释或标点符号。\n    # 扩写用提示词模板（当描述详细时使用）\n    expand: |\n      你是一个专业的AI图像生成提示词助手。用户提供了一个详细的图像描述，请使用思维链的方式，逐步将其转换为NovelAI图像生成所需的英文提示词。严禁直接返回用户原本的输入内容!!!\n      \n      转换步骤：\n      \n      第一步：识别角色出处\n      - 思考：描述中是否出现疑似有作品出处的角色名称？\n      - 行动：若有，请利用联网搜索功能，先用中文查找其官方英文名，再用该英文名查询其在 danbooru 网站中的准确 tag 名，并在最终输出中使用这个名字。\n      \n      第二步：理解并提取核心元素\n      - 思考：用户描述中的主要对象是什么？（人物、动物、物体、场景等）\n      - 思考：描述中提到了哪些关键特征？（外貌、服装、动作、表情等）\n      - 思考：描述中体现了什么风格或氛围？（艺术风格、情绪、主题等）\n      - 行动：提取并记录这些核心元素，确保不遗漏重要信息。\n      \n      第三步：识别构图和视角信息\n      - 思考：描述中是否包含构图信息？（全身、半身、特写、远景、中景、近景等）\n      - 思考：描述中是否包含视角信息？（正面、侧面、背面、仰视、俯视、平视等）\n      - 行动：将这些构图和视角信息转换为对应的英文tag。\n      \n      第四步：识别背景和环境信息\n      - 思考：描述中是否包含背景信息？（室内、室外、具体场景、抽象背景等）\n      - 思考：背景的具体特征是什么？（房间类型、自然环境、城市景观等）\n      - 行动：将背景信息转换为对应的英文tag或自然语言描述。\n      \n      第五步：转换为danbooru风格的tag\n      - 思考：哪些元素可以用danbooru数据库的tag准确描述？（人物特征、服装、姿势、表情等）\n      - 思考：哪些元素难以用tag描述，需要用自然语言？（复杂场景、抽象概念、特定风格等）\n      - 行动：优先使用danbooru风格的tag，难以用tag描述的部分使用简洁的英文自然语言。\n      \n      第六步：组织提示词结构\n      - 思考：如何组织提示词的顺序？（通常：主体 → 特征 → 动作/姿势 → 服装/装饰 → 背景 → 风格）\n      - 思考：如何确保提示词清晰、具体、易于理解？\n      - 行动：按照合理的顺序组织tag和自然语言，用逗号分隔，确保流畅可读。\n      \n      第七步：最终检查\n      - 检查：是否完全使用英文？（除非用户明确要求其他语言）\n      - 检查：是否保持了原描述的核心元素和风格？\n      - 检查：是否只包含提示词文本，没有添加负面词条、分辨率等参数？\n      - 检查：是否没有附加质量词（如 best quality、masterpiece 等）？\n      - 检查：是否没有直接返回用户原本的输入内容？\n      \n      用户描述：{user_input}\n      \n      请在内部完成全部分析过程，不要输出任何推理、步骤说明或解释。最后只输出转换后的英文提示词，不要添加任何解释、前缀或后缀。\n    # 翻译用提示词模板（当描述不详细时使用）\n    translate: |\n      你是一个专业的AI图像生成提示词助手。用户提供了一个简单的图像描述，请使用思维链的方式，逐步将其翻译并扩展为NovelAI图像生成所需的英文提示词。严禁直接返回用户原本的输入内容!!!\n      \n      转换步骤：\n      \n      第一步：识别角色出处\n      - 思考：描述中是否出现疑似有作品出处的角色名称？\n      - 行动：若有，请利用联网搜索功能，先用中文查找其官方英文名，再用该英文名查询其在 danbooru 网站中的准确 tag 名，并在最终输出中使用这个名字。\n      \n      第二步：理解用户意图\n      - 思考：用户描述的核心内容是什么？（主要对象、基本特征等）\n      - 思考：用户可能想要什么样的图像？（风格、氛围、主题等）\n      - 行动：识别并记录用户描述中的关键信息，理解用户的真实意图。\n      \n      第三步：翻译为英文\n      - 思考：如何将用户描述准确翻译为英文？\n      - 思考：如何保持原意的同时使用地道的英文表达？\n      - 行动：将用户描述翻译为英文，确保准确传达原意。\n      \n      第四步：识别缺失的信息\n      - 思考：描述中缺少哪些重要信息？（主体特征、构图、视角、背景、风格等）\n      - 思考：哪些信息对于生成清晰的图像是必要的？\n      - 行动：识别并记录需要补充的信息类别。\n      \n      第五步：合理扩展描述\n      - 思考：如何补充主体特征？（外貌、体型、年龄等）\n      - 思考：如何补充构图和视角信息？（全身/半身/特写、正面/侧面等）\n      - 思考：如何补充背景信息？（室内/室外、具体场景等）\n      - 思考：如何补充风格信息？（艺术风格、画风等）\n      - 行动：根据用户描述的核心内容，合理扩展并添加必要的细节，确保扩展内容与用户意图一致。\n      \n      第六步：转换为danbooru风格的tag\n      - 思考：哪些元素可以用danbooru数据库的tag准确描述？（人物特征、服装、姿势、表情等）\n      - 思考：哪些元素难以用tag描述，需要用自然语言？（复杂场景、抽象概念、特定风格等）\n      - 行动：优先使用danbooru风格的tag，难以用tag描述的部分使用简洁的英文自然语言。\n      \n      第七步：组织提示词结构\n      - 思考：如何组织提示词的顺序？（通常：主体 → 特征 → 动作/姿势 → 服装/装饰 → 背景 → 风格）\n      - 思考：如何确保提示词清晰、具体、易于理解？\n      - 行动：按照合理的顺序组织tag和自然语言，用逗号分隔，确保流畅可读。\n      \n      第八步：最终检查\n      - 检查：是否完全使用英文？\n      - 检查：是否在保持用户意图的基础上合理扩展了描述？\n      - 检查：是否只包含提示词文本，没有添加负面词条、分辨率等参数？\n      - 检查：是否没有附加质量词（如 best quality、masterpiece 等）？\n      - 检查：是否没有直接返回用户原本的输入内容？\n      - 检查：提示词是否清晰、具体，包含必要的细节？\n      \n      用户描述：{user_input}\n      \n      请在内部完成全部分析过程，不要输出任何推理、步骤说明或解释。最后只输出翻译并扩展后的英文提示词，不要添加任何解释、前缀或后缀。\n"""


@dataclass
class NLSettings:
    """自然语言处理设置。"""
    quality_words_override: str
    negative_preset_override: str
    llm_provider: str
    openrouter_api_key: str
    openrouter_models: list[str]
    openrouter_timeout: int
    openrouter_http_referer: Optional[str]
    openrouter_x_title: Optional[str]
    prompt_templates: dict[str, str]


@dataclass
class PluginConfig:
    nai_token: str
    proxy: Optional[str]
    default_model: str
    image_save_path: str
    default_daily_limit: int
    admin_qq_list: list[str]
    preset_uc: str
    quality_words: str
    nl_settings: Optional[NLSettings] = None


@dataclass
class PlatformProfile:
    platform_name: str
    access_control: AccessControl
    whitelist_path: Path
    use_group_whitelist: bool


def _load_yaml_config(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("未安装 PyYAML，请执行 pip install PyYAML")
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        return {}
    return data


def _ensure_model(model: str) -> str:
    if model not in MODELS:
        raise ValueError(f"模型无效: {model}")
    return model


@register("novelai_img_generation", "NeoBerekov", "NovelAI 图片生成", "1.0.0")
class NovelAIPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.context = context
        self.plugin_dir = Path(__file__).parent
        # 配置文件放在插件文件夹内
        self.config_path = self.plugin_dir / "config.yaml"
        # 数据文件夹（用于存放各平台的 whitelist.json）
        self.data_dir = self.plugin_dir / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        # 迁移旧配置文件（如果存在）
        self._migrate_config_files()
        # 确保默认配置文件存在
        self._ensure_default_config()
        # 确保所有平台的 whitelist 文件存在
        self._ensure_default_whitelists()
        self.config = self._load_config()
        self.platform_profiles: dict[str, PlatformProfile] = {}
        self.nai_api: Optional[NovelAIAPI] = None
        self._init_error: Optional[str] = None
        self._init_nai_api()
        self.nl_processor: Optional[NLProcessor] = None
        self._init_nl_processor()
        self.request_queue = RequestQueue(self._process_queue_item)

    async def initialize(self):
        await self.request_queue.start()

    async def terminate(self):
        await self.request_queue.stop()
        if self.nai_api:
            await self.nai_api.close()
        if self.nl_processor and self.nl_processor.llm_client:
            await self.nl_processor.llm_client.close()

    def _load_config(self) -> PluginConfig:
        defaults = {
            "nai_token": "",
            "proxy": None,
            "default_model": "nai-diffusion-4-5-curated",
            "image_save_path": str((self.plugin_dir / "outputs").resolve()),
            "default_daily_limit": 10,
            "admin_qq_list": [],
            "preset_uc": "",
            "quality_words": "best quality, masterpiece",
        }
        user_config = _load_yaml_config(self.config_path)
        merged = {**defaults, **user_config}
        try:
            default_model = _ensure_model(merged["default_model"])
        except Exception:  # noqa: BLE001
            default_model = defaults["default_model"]
        image_path = Path(str(merged.get("image_save_path", defaults["image_save_path"])) )
        if not image_path.is_absolute():
            image_path = (self.plugin_dir / image_path).resolve()
        
        # 加载自然语言设置
        nl_settings = None
        nl_config = merged.get("nl_settings", {})
        if nl_config and isinstance(nl_config, dict):
            openrouter_config = nl_config.get("openrouter", {})
            prompt_templates = nl_config.get("prompt_templates", {})
            nl_settings = NLSettings(
                quality_words_override=str(nl_config.get("quality_words_override", "") or ""),
                negative_preset_override=str(nl_config.get("negative_preset_override", "") or ""),
                llm_provider=str(nl_config.get("llm_provider", "openrouter")),
                openrouter_api_key=str(openrouter_config.get("api_key", "") or ""),
                openrouter_models=list(openrouter_config.get("models", ["openai/gpt-4o-mini"])),
                openrouter_timeout=int(openrouter_config.get("timeout", 30)),
                openrouter_http_referer=openrouter_config.get("http_referer") or None,
                openrouter_x_title=openrouter_config.get("x_title") or None,
                prompt_templates={
                    "detail_check": str(prompt_templates.get("detail_check", "")),
                    "expand": str(prompt_templates.get("expand", "")),
                    "translate": str(prompt_templates.get("translate", "")),
                },
            )
        
        return PluginConfig(
            nai_token=str(merged.get("nai_token", "")),
            proxy=merged.get("proxy") or None,
            default_model=default_model,
            image_save_path=str(image_path),
            default_daily_limit=int(merged.get("default_daily_limit", 10)),
            admin_qq_list=[str(x) for x in merged.get("admin_qq_list", [])],
            preset_uc=str(merged.get("preset_uc", "") or ""),
            quality_words=str(merged.get("quality_words", "") or ""),
            nl_settings=nl_settings,
        )

    def _ensure_ready(self) -> Optional[str]:
        if self._init_error:
            return f"插件初始化失败：{self._init_error}"
        if not self.nai_api:
            return "NovelAI API 未初始化"
        if not self.config.nai_token:
            return "未配置 NovelAI Token"
        return None

    @filter.command("nai")
    async def generate_image(self, event: AstrMessageEvent):
        error = self._ensure_ready()
        if error:
            yield event.plain_result(error)
            return

        profile = self._get_platform_profile(event)
        access_control = profile.access_control

        is_group = self._is_group_message(event)
        group_id = event.get_group_id() if is_group else ""

        if is_group and profile.use_group_whitelist:
            if not await access_control.check_group_permission(group_id):
                return

        command_text = self._extract_command_text(event)
        if not command_text and event.get_platform_name().lower() == "discord":
            command_text = self._extract_discord_command_text(event)

        if not command_text:
            if not is_group:
                yield event.plain_result("未识别到指令")
            return

        try:
            parsed = parse_generation_message(command_text)
        except ParseError as exc:
            if event.get_platform_name().lower() == "discord" and hasattr(event.message_obj, "raw_message"):
                raw = event.message_obj.raw_message
                cleaned = self._extract_discord_command_text(event)
                if cleaned:
                    try:
                        parsed = parse_generation_message(f"/nai {cleaned}")
                    except ParseError:
                        yield event.plain_result(str(exc))
                        return
                else:
                    yield event.plain_result(str(exc))
                    return
            else:
                yield event.plain_result(str(exc))
                return

        model = parsed.model_name or self.config.default_model
        if model not in MODELS:
            if not is_group:
                yield event.plain_result("模型参数无效")
            return

        user_id = event.get_sender_id()
        user_allowed = await access_control.check_permission(user_id)
        if not user_allowed:
            if not is_group:
                yield event.plain_result("您不在白名单中")
            return

        if not await access_control.check_quota(user_id):
            if not is_group:
                yield event.plain_result("每日限额已达")
            return

        try:
            base_image, character_reference = await self._extract_images(event, parsed)
        except ValueError as exc:
            if not is_group:
                yield event.plain_result(str(exc))
            return

        assert self.nai_api is not None
        try:
            payload, seed = self.nai_api.build_payload(
                parsed,
                model=model,
                base_image=base_image,
                character_reference=character_reference,
            )
        except NovelAIAPIError as exc:
            if not is_group:
                yield event.plain_result(str(exc))
            return

        await self.request_queue.enqueue(
            {
                "event": event,
                "payload": payload,
                "user_id": user_id,
                "sender_name": event.get_sender_name() or user_id,
                "model": model,
                "seed": seed,
                "parsed": parsed,
            },
        )

        hint = "已加入生成队列，请稍候~"
        if parsed.auto_positive:
            hint += " (未检测到‘正面词条’项，将全文作为提示词进行生图)"
        yield event.plain_result(hint)

    async def _process_queue_item(self, item: dict[str, Any]):
        event: AstrMessageEvent = item["event"]
        user_id = item["user_id"]
        sender_name = item["sender_name"]
        model = item["model"]
        seed = item["seed"]
        payload = item["payload"]
        llm_model_name = item.get("llm_model")

        profile = self._get_platform_profile(event)
        access_control = profile.access_control

        if not self.nai_api:
            await self._send_text(event, sender_name, user_id, "NovelAI 服务未就绪")
            return

        try:
            image_bytes = await self.nai_api.generate_image(payload)
            file_path = self._store_image(image_bytes, model, seed)
            await access_control.consume_quota(user_id)
            chain = MessageChain()
            chain.chain.append(At(name=sender_name, qq=user_id))
            result_text = f"图片生成完成！模型: {model}，种子: {seed}"
            if llm_model_name:
                result_text += f"，LLM: {llm_model_name}"
            chain.chain.append(Plain(result_text))
            chain.chain.append(Image.fromFileSystem(file_path))
            await event.send(chain)
            await self._try_recall_request(event)
        except NovelAIAPIError as exc:
            await self._send_text(event, sender_name, user_id, f"生成失败：{exc}")
        except Exception as exc:  # noqa: BLE001
            logger.error(f"NovelAI生成异常: {exc}", exc_info=True)
            await self._send_text(event, sender_name, user_id, "生成失败，请稍后重试")

    async def _send_text(self, event: AstrMessageEvent, name: str, qq: str, text: str):
        chain = MessageChain()
        chain.chain.append(At(name=name, qq=qq))
        chain.chain.append(Plain(text))
        await event.send(chain)

    def _extract_command_text(self, event: AstrMessageEvent) -> str:
        parts: list[str] = []
        for comp in event.get_messages():
            if isinstance(comp, Plain):
                parts.append(comp.text)
        return "".join(parts).strip()

    def _extract_discord_command_text(self, event: AstrMessageEvent) -> str:
        raw = getattr(event.message_obj, "raw_message", None)
        if not raw:
            return ""
        try:
            data = getattr(raw, "data", None)
            if isinstance(data, dict) and data.get("options"):
                values: list[str] = []
                for option in data.get("options", []):
                    if isinstance(option, dict):
                        value = option.get("value")
                        if value is not None:
                            values.append(str(value))
                if values:
                    return " ".join(values).strip()
        except Exception:  # noqa: BLE001 - Fallback to clean_content
            pass

        clean_content = getattr(raw, "clean_content", "")
        cleaned = clean_content.strip()
        if cleaned.lower().startswith("/nai"):
            cleaned = cleaned[len("/nai"):].strip()
        return cleaned

    def _is_admin(self, event: AstrMessageEvent) -> bool:
        user_id = event.get_sender_id()
        return event.is_admin() or user_id in self.config.admin_qq_list

    def _is_group_message(self, event: AstrMessageEvent) -> bool:
        return bool(event.get_group_id())

    def _resolve_target(self, event: AstrMessageEvent, target: str) -> Tuple[Optional[str], Optional[str]]:
        messages = list(event.get_messages())
        at_components = [
            comp
            for comp in messages
            if isinstance(comp, At) and str(comp.qq) != event.get_self_id()
        ]

        raw_message = getattr(event.message_obj, "raw_message", None)
        is_discord = event.get_platform_name().lower() == "discord"

        cleaned = target.strip()
        if is_discord and not cleaned and raw_message is not None:
            options = getattr(getattr(raw_message, "data", None), "get", lambda _: None)("options")
            if options:
                cleaned = " ".join(str(opt.get("value", "")) for opt in options if opt.get("value"))
            if not cleaned:
                cleaned = getattr(raw_message, "clean_content", "").strip()

        if cleaned:
            mention_match = re.fullmatch(r"<@!?([0-9]+)>", cleaned)
            if mention_match:
                user_id = mention_match.group(1)
                nickname = None
                if is_discord:
                    nickname = self._fetch_discord_member_name(raw_message, user_id)
                return user_id, nickname or user_id

            cleaned = cleaned.lstrip("@")
            for comp in at_components:
                qq_str = str(comp.qq)
                comp_name = (comp.name or "").strip() or None
                if cleaned == qq_str or (comp_name and cleaned == comp_name):
                    nickname = comp_name or cleaned
                    if is_discord:
                        nickname = self._fetch_discord_member_name(raw_message, qq_str) or nickname
                    return qq_str, nickname
            if len(at_components) == 1:
                comp = at_components[0]
                qq_str = str(comp.qq)
                nickname = cleaned or (comp.name or None)
                if is_discord:
                    nickname = self._fetch_discord_member_name(raw_message, qq_str) or nickname
                return qq_str, nickname
            digits = re.search(r"\d{5,}", cleaned)
            if digits:
                qq_val = digits.group(0)
                nick = cleaned.replace(qq_val, "").strip()
                nick = nick.strip("()（）") or None
                if is_discord:
                    nick = self._fetch_discord_member_name(raw_message, qq_val) or nick
                return qq_val, nick or cleaned
            if is_discord:
                nick = self._fetch_discord_member_name(raw_message, cleaned)
                if nick:
                    return cleaned, nick
            return cleaned, cleaned or None

        if at_components:
            comp = at_components[0]
            comp_name = (comp.name or "").strip() or None
            nick = comp_name
            if is_discord:
                nick = self._fetch_discord_member_name(raw_message, str(comp.qq)) or nick
            return str(comp.qq), nick

        return None, None

    def _resolve_group_target(
        self,
        event: AstrMessageEvent,
        target: str,
        name: str,
    ) -> Tuple[Optional[str], Optional[str]]:
        target = (target or "").strip()
        provided_name = (name or "").strip() or None

        if target in ("", "本群", "当前", "此群"):
            group_id = event.get_group_id()
            if not group_id:
                return None, None
            group_name = provided_name or self._get_group_name(event)
            return group_id, group_name

        digits = re.search(r"\d{5,}", target)
        if digits:
            group_id = digits.group(0)
            group_name = provided_name or target.replace(group_id, "").strip(" ()（）") or None
            return group_id, group_name

        return target, provided_name or None

    def _get_group_name(self, event: AstrMessageEvent) -> Optional[str]:
        group = getattr(event.message_obj, "group", None)
        if group and getattr(group, "group_name", None):
            return group.group_name
        return None

    async def _bot_is_group_admin(self, event: AstrMessageEvent) -> bool:
        if not self._is_group_message(event):
            return False
        try:
            group = await event.get_group()
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"获取群信息失败，无法判定管理员权限: {exc}")
            return False
        if not group:
            return False
        self_id = str(event.get_self_id())
        if str(group.group_owner or "") == self_id:
            return True
        admins = getattr(group, "group_admins", None) or []
        return self_id in {str(admin) for admin in admins}

    async def _try_recall_request(self, event: AstrMessageEvent) -> None:
        if not self._is_group_message(event):
            return
        if not await self._bot_is_group_admin(event):
            return
        message_id = getattr(event.message_obj, "message_id", None)
        if not message_id:
            return
        await self._recall_message(event, message_id)

    async def _recall_message(self, event: AstrMessageEvent, message_id: str | int) -> None:
        platform = event.get_platform_name()
        try:
            if platform == "aiocqhttp" and hasattr(event, "bot"):
                payload_id = message_id
                try:
                    payload_id = int(message_id)
                except (TypeError, ValueError):
                    pass
                await event.bot.call_action("delete_msg", message_id=payload_id)
            else:
                logger.debug(f"当前平台 {platform} 暂未实现自动撤回功能")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"撤回消息失败: {exc}")

    async def _extract_images(
        self,
        event: AstrMessageEvent,
        parsed: ParsedParams,
    ) -> tuple[Optional[str], Optional[str]]:
        images = [comp for comp in event.get_messages() if isinstance(comp, Image)]
        if not images:
            if parsed.base_image or parsed.character_reference:
                raise ValueError("消息中未找到图片，请先发送图片")
            return None, None

        image_map = {str(idx + 1): img for idx, img in enumerate(images)}

        base_image_data = None
        if parsed.base_image:
            target = image_map.get(parsed.base_image.strip())
            if not target:
                raise ValueError("未找到指定的底图，请确认图片编号")
            base_image_data = await self._image_component_to_base64(target)

        character_reference_data = None
        if parsed.character_reference:
            target = image_map.get(parsed.character_reference.strip())
            if not target:
                raise ValueError("未找到指定的角色参考图，请确认图片编号")
            character_reference_data = await self._image_component_to_base64(target)

        return base_image_data, character_reference_data

    async def _image_component_to_base64(self, image: Image) -> str:
        if image.file and image.file.startswith("base64://"):
            return image.file.removeprefix("base64://")
        if image.file and image.file.startswith("file:///"):
            path = image.file.replace("file:///", "")
            return image_to_base64(path)
        if image.file and os.path.exists(image.file):
            return image_to_base64(image.file)
        file_path = await image.convert_to_file_path()
        return image_to_base64(file_path)

    def _store_image(self, image_bytes: bytes, model: str, seed: int) -> str:
        save_dir = Path(self.config.image_save_path)
        if not save_dir.is_absolute():
            save_dir = self.plugin_dir / save_dir
        save_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{model}_{seed}.png"
        file_path = save_dir / filename
        save_image_from_bytes(image_bytes, str(file_path))
        return str(file_path)

    @filter.command_group("nai白名单")
    def whitelist_group(self):
        pass

    @whitelist_group.command("添加")
    async def whitelist_add(self, event: AstrMessageEvent, target: str = "", nickname: str = ""):
        if not self._is_admin(event):
            yield event.plain_result("仅管理员可执行此操作")
            return
        access_control = self._get_platform_profile(event).access_control
        qq, default_name = self._resolve_target(event, target)
        if not qq:
            yield event.plain_result("请提供要添加的QQ号或@目标")
            return
        nick = nickname.strip() or default_name
        user = await access_control.add_to_whitelist(qq, nickname=nick)
        yield event.plain_result(
            f"已添加 {qq} 至白名单，昵称：{user.nickname or '未设'}，今日剩余 {user.remaining}/{user.daily_limit} 次",
        )

    @whitelist_group.command("删除")
    async def whitelist_remove(self, event: AstrMessageEvent, target: str = ""):
        if not self._is_admin(event):
            yield event.plain_result("仅管理员可执行此操作")
            return
        access_control = self._get_platform_profile(event).access_control
        qq, _ = self._resolve_target(event, target)
        if not qq:
            yield event.plain_result("请提供要删除的QQ号或@目标")
            return
        removed = await access_control.remove_from_whitelist(qq)
        if removed:
            yield event.plain_result(f"已从白名单移除 {qq}")
        else:
            yield event.plain_result("目标不在白名单中")

    @filter.command_group("nai限额")
    def quota_group(self):
        pass

    @quota_group.command("设置")
    async def quota_set(self, event: AstrMessageEvent, target: str = "", limit: str = "", nickname: str = ""):
        if not self._is_admin(event):
            yield event.plain_result("仅管理员可执行此操作")
            return
        access_control = self._get_platform_profile(event).access_control
        qq, default_name = self._resolve_target(event, target)
        if not qq:
            yield event.plain_result("请提供要设置的QQ号或@目标")
            return
        try:
            limit_value = int(limit)
        except ValueError:
            yield event.plain_result("限额必须是整数")
            return
        try:
            nick = nickname.strip() or default_name
            user = await access_control.set_quota(qq, limit_value, nickname=nick)
        except ValueError as exc:
            yield event.plain_result(str(exc))
            return
        yield event.plain_result(
            f"已将 {qq}（昵称：{user.nickname or '未设'}）的每日限额设置为 {user.daily_limit}，今日剩余 {user.remaining}",
        )

    @filter.command("nai插件重启")
    async def reload_plugin(self, event: AstrMessageEvent):
        if not self._is_admin(event):
            yield event.plain_result("仅管理员可执行此操作")
            return

        success, message = await self._reload_config_from_file()
        yield event.plain_result(message)
        if success:
            logger.info("NovelAI 插件配置已重新加载")

    @filter.command_group("nai群白名单")
    def group_whitelist_group(self):
        pass

    @group_whitelist_group.command("添加")
    async def group_whitelist_add(self, event: AstrMessageEvent, target: str = "", name: str = ""):
        if not self._is_admin(event):
            yield event.plain_result("仅管理员可执行此操作")
            return
        profile = self._get_platform_profile(event)
        access_control = profile.access_control
        group_id, group_name = self._resolve_group_target(event, target, name)
        if not group_id:
            yield event.plain_result("请提供群号，或在目标群内使用该命令")
            return
        entry = await access_control.add_group(group_id, group_name)
        yield event.plain_result(
            f"已添加群 {group_id} 至白名单，名称：{entry.get('name') or '未设'}",
        )

    @group_whitelist_group.command("删除")
    async def group_whitelist_remove(self, event: AstrMessageEvent, target: str = ""):
        if not self._is_admin(event):
            yield event.plain_result("仅管理员可执行此操作")
            return
        access_control = self._get_platform_profile(event).access_control
        group_id, _ = self._resolve_group_target(event, target, "")
        if not group_id:
            yield event.plain_result("请提供群号，或在目标群内使用该命令")
            return
        removed = await access_control.remove_group(group_id)
        if removed:
            yield event.plain_result(f"已从群白名单移除 {group_id}")
        else:
            yield event.plain_result("该群不在白名单中")

    @filter.command("nai_whitelist_add")
    async def whitelist_add_en(self, event: AstrMessageEvent, target: str = "", nickname: str = ""):
        async for result in self.whitelist_add(event, target, nickname):
            yield result

    @filter.command("nai_whitelist_remove")
    async def whitelist_remove_en(self, event: AstrMessageEvent, target: str = ""):
        async for result in self.whitelist_remove(event, target):
            yield result

    @filter.command("naihelp")
    async def nai_help(self, event: AstrMessageEvent):
        template = (
            "/nai 正面词条:<主要提示词，必填>\n"
            "     负面词条:<不需要的内容；留空则使用配置 preset_uc>\n"
            "     是否有福瑞:<是/否，默认否；是时会在提示词前添加 fur dataset>\n"
            "     添加质量词:<是/否，默认否；关闭时若缺少 best quality/masterpiece 会自动追加配置 quality_words>\n"
            "     底图:<图生图使用的图片编号，留空为文本生图>\n"
            "     底图重绘强度:<0~1，默认0.7；越低越接近原图>\n"
            "     底图加噪强度:<0~0.99，默认0；越高越接近文本描述>\n"
            "     分辨率:<竖图/横图/方图，默认竖图>\n"
            "     步数:<1~28 的整数，默认28>\n"
            "     指导系数:<0~10 的数字，默认5>\n"
            "     重采样系数:<0~1 的数字，默认0>\n"
            "     种子:<整数，留空则随机>\n"
            "     采样器:<k_euler/k_euler_ancestral/k_dpmpp_2m/...，默认 k_euler_ancestral>\n"
            "     角色是否分区:<是/否；是时可指定角色位置，默认根据角色数判断>\n"
            "     角色1正面词条:<角色提示词> 角色1负面词条:<角色负面词条> 角色1位置:<A1~E5>\n"
            "     角色参考:<角色参考图编号> 角色参考强度:<0~1，默认1>\n"
            "     是否注意原画风:<是/否，默认否>\n"
            "     模型:<模型名称，留空使用配置 default_model>\n"
        )
        yield event.plain_result(template)

    @filter.command("nainl")
    async def generate_image_nl(self, event: AstrMessageEvent):
        """使用自然语言描述生成图片。"""
        # 检查 NL 处理器是否可用
        if not self.nl_processor:
            error_msg = "自然语言处理功能未启用，请检查配置中的 nl_settings"
            if not self._is_group_message(event):
                yield event.plain_result(error_msg)
            return

        error = self._ensure_ready()
        if error:
            yield event.plain_result(error)
            return

        profile = self._get_platform_profile(event)
        access_control = profile.access_control

        is_group = self._is_group_message(event)
        group_id = event.get_group_id() if is_group else ""

        if is_group and profile.use_group_whitelist:
            if not await access_control.check_group_permission(group_id):
                return

        user_id = event.get_sender_id()
        user_allowed = await access_control.check_permission(user_id)
        if not user_allowed:
            if not is_group:
                yield event.plain_result("您不在白名单中")
            return

        if not await access_control.check_quota(user_id):
            if not is_group:
                yield event.plain_result("每日限额已达")
            return

        # 提取用户输入
        user_input = self._extract_command_text(event)
        if not user_input and event.get_platform_name().lower() == "discord":
            user_input = self._extract_discord_command_text(event)

        # 移除命令前缀（支持大小写不敏感）
        user_input_lower = user_input.lower()
        if user_input_lower.startswith("/nainl"):
            user_input = user_input[6:].strip()
        elif user_input_lower.startswith("nainl"):
            user_input = user_input[5:].strip()

        auto_add_quality_words = True
        natural_language_input = user_input
        extracted_positive_prompt = None

        # 尝试解析键值对格式的参数
        try:
            # 使用临时命令格式来解析参数
            temp_command = f"/nai {user_input}"
            parsed_temp = parse_generation_message(temp_command)
            
            # 检查是否提供了"是否自动添加质量词"参数
            auto_add_pattern = r"是否自动添加(?:质量词|提示词)[：:]\s*<([^>]+)>"
            match = re.search(auto_add_pattern, user_input, re.IGNORECASE)
            if match:
                value = match.group(1).strip().lower()
                auto_add_quality_words = value in ["是", "yes", "true", "1"]
                # 从输入中移除这个参数
                natural_language_input = re.sub(auto_add_pattern, "", user_input, flags=re.IGNORECASE).strip()
            else:
                natural_language_input = user_input

            # 检查是否直接提供了"正面词条"参数
            if parsed_temp.positive_prompt and not parsed_temp.auto_positive:
                extracted_positive_prompt = parsed_temp.positive_prompt
                positive_pattern = r"正面词条[：:]\s*<[^>]+>"
                natural_language_input = re.sub(positive_pattern, "", natural_language_input, flags=re.IGNORECASE).strip()
        except ParseError:
            # 如果解析失败，说明是纯自然语言输入，使用默认值
            pass

        # 构造用于 LLM 的自然语言描述
        natural_language_input = natural_language_input.strip()
        if not natural_language_input and extracted_positive_prompt:
            natural_language_input = extracted_positive_prompt.strip()

        if not natural_language_input:
            if not is_group:
                yield event.plain_result("请输入图像描述")
            return

        yield event.plain_result("自然语言交由 LLM 分析中，请稍后~")

        # 始终通过 LLM 转换自然语言
        try:
            nl_result = await self.nl_processor.process(
                natural_language_input,
                auto_add_quality_words=auto_add_quality_words,
                quality_words=self.config.quality_words,
            )
            converted_params = nl_result.params_text
            llm_model_used = nl_result.model_name
            parsed_converted = parse_generation_message(f"/nai {converted_params}")
            positive_prompt = parsed_converted.positive_prompt
        except NLProcessingError as exc:
            if not is_group:
                yield event.plain_result(f"自然语言处理失败：{exc}")
            return
        except ParseError as exc:
            if not is_group:
                yield event.plain_result(f"参数解析失败：{exc}")
            return

        # 构建完整的命令文本
        command_text = f"/nai 正面词条:<{positive_prompt}>"

        # 应用质量词和负面词条覆盖（如果有）
        nl_settings = self.config.nl_settings
        if nl_settings:
            # 解析参数
            try:
                parsed = parse_generation_message(command_text)
            except ParseError as exc:
                if not is_group:
                    yield event.plain_result(f"参数解析失败：{exc}")
                return

            # 应用覆盖
            if nl_settings.quality_words_override and not parsed.positive_prompt:
                # 如果 NL 处理器没有生成正面词条，使用覆盖的质量词
                if converted_params:
                    command_text = f"/nai 正面词条:<{nl_settings.quality_words_override}> {converted_params}"
                else:
                    command_text = f"/nai 正面词条:<{nl_settings.quality_words_override}>"
            elif nl_settings.quality_words_override:
                # 在现有参数基础上添加质量词覆盖提示
                # 这里我们通过修改解析后的参数来实现
                pass  # 暂时不修改，让用户手动控制

            if nl_settings.negative_preset_override and not parsed.negative_prompt:
                # 如果 NL 处理器没有生成负面词条，添加覆盖的负面词条
                if "负面词条" not in command_text:
                    command_text = f"{command_text} 负面词条:<{nl_settings.negative_preset_override}>"

            # 重新解析（如果修改了 command_text）
            try:
                parsed = parse_generation_message(command_text)
            except ParseError as exc:
                if not is_group:
                    yield event.plain_result(f"参数解析失败：{exc}")
                return
        else:
            # 没有 NL 设置，直接解析
            try:
                parsed = parse_generation_message(command_text)
            except ParseError as exc:
                if not is_group:
                    yield event.plain_result(f"参数解析失败：{exc}")
                return

        # 应用质量词覆盖到配置（临时）
        original_quality_words = self.config.quality_words
        original_preset_uc = self.config.preset_uc
        if nl_settings:
            if nl_settings.quality_words_override:
                self.config.quality_words = nl_settings.quality_words_override
            if nl_settings.negative_preset_override:
                self.config.preset_uc = nl_settings.negative_preset_override

        model = parsed.model_name or self.config.default_model
        if model not in MODELS:
            if not is_group:
                yield event.plain_result("模型参数无效")
            # 恢复原始配置
            self.config.quality_words = original_quality_words
            self.config.preset_uc = original_preset_uc
            return

        try:
            base_image, character_reference = await self._extract_images(event, parsed)
        except ValueError as exc:
            if not is_group:
                yield event.plain_result(str(exc))
            # 恢复原始配置
            self.config.quality_words = original_quality_words
            self.config.preset_uc = original_preset_uc
            return

        assert self.nai_api is not None
        
        # 临时更新 API 的质量词和负面词条
        original_api_quality = self.nai_api.quality_words
        original_api_preset = self.nai_api.preset_uc
        if nl_settings:
            if nl_settings.quality_words_override:
                self.nai_api.quality_words = nl_settings.quality_words_override
            if nl_settings.negative_preset_override:
                self.nai_api.preset_uc = nl_settings.negative_preset_override

        try:
            payload, seed = self.nai_api.build_payload(
                parsed,
                model=model,
                base_image=base_image,
                character_reference=character_reference,
            )
        except NovelAIAPIError as exc:
            if not is_group:
                yield event.plain_result(str(exc))
            # 恢复配置
            self.config.quality_words = original_quality_words
            self.config.preset_uc = original_preset_uc
            self.nai_api.quality_words = original_api_quality
            self.nai_api.preset_uc = original_api_preset
            return
        finally:
            # 恢复配置
            self.config.quality_words = original_quality_words
            self.config.preset_uc = original_preset_uc
            self.nai_api.quality_words = original_api_quality
            self.nai_api.preset_uc = original_api_preset

        await self.request_queue.enqueue(
            {
                "event": event,
                "payload": payload,
                "user_id": user_id,
                "sender_name": event.get_sender_name() or user_id,
                "model": model,
                "seed": seed,
                "parsed": parsed,
                "llm_model": llm_model_used,
            },
        )

        hint = "已加入生成队列（自然语言模式），请稍候~"
        yield event.plain_result(hint)

    def _init_nai_api(self):
        self._init_error = None
        try:
            if not self.config.nai_token:
                raise NovelAIAPIError("未配置 NovelAI Token")
            self.nai_api = NovelAIAPI(
                self.config.nai_token,
                proxy=self.config.proxy,
                quality_words=self.config.quality_words,
                preset_uc=self.config.preset_uc,
            )
        except NovelAIAPIError as exc:
            self.nai_api = None
            self._init_error = str(exc)
            logger.error(f"NovelAI API 初始化失败: {exc}")

    def _init_nl_processor(self):
        """初始化自然语言处理器。"""
        if not self.config.nl_settings:
            logger.debug("未配置自然语言处理设置，/nainl 功能不可用")
            return

        nl_settings = self.config.nl_settings
        if nl_settings.llm_provider != "openrouter":
            logger.warning(f"不支持的 LLM 提供商: {nl_settings.llm_provider}")
            return

        if not nl_settings.openrouter_api_key:
            logger.warning("未配置 OpenRouter API Key，/nainl 功能不可用")
            return

        if not nl_settings.openrouter_models:
            logger.warning("未配置 OpenRouter 模型列表，/nainl 功能不可用")
            return

        try:
            llm_client = OpenRouterLLMClient(
                api_key=nl_settings.openrouter_api_key,
                models=nl_settings.openrouter_models,
                proxy=self.config.proxy,
                timeout=nl_settings.openrouter_timeout,
                http_referer=nl_settings.openrouter_http_referer,
                x_title=nl_settings.openrouter_x_title,
            )
            self.nl_processor = NLProcessor(
                llm_client=llm_client,
                prompt_templates=nl_settings.prompt_templates,
            )
            logger.info("自然语言处理器初始化成功")
        except LLMError as exc:
            logger.error(f"自然语言处理器初始化失败: {exc}")
            self.nl_processor = None

    async def _reset_api(self):
        if self.nai_api:
            await self.nai_api.close()
        self._init_nai_api()

    async def _reset_nl_processor(self):
        """重置自然语言处理器。"""
        if self.nl_processor and self.nl_processor.llm_client:
            await self.nl_processor.llm_client.close()
        self.nl_processor = None
        self._init_nl_processor()

    async def _reload_config_from_file(self) -> Tuple[bool, str]:
        self._ensure_default_config()
        try:
            new_config = self._load_config()
        except RuntimeError as exc:
            return False, str(exc)

        self.config = new_config
        for profile in self.platform_profiles.values():
            profile.access_control.default_daily_limit = self.config.default_daily_limit

        await self._reset_api()
        await self._reset_nl_processor()
        if self._init_error:
            return False, f"配置重载完成，但 NovelAI 初始化失败：{self._init_error}"
        return True, "插件配置已重新加载"

    def _migrate_config_files(self) -> None:
        """迁移旧位置的配置文件到插件目录。"""
        # 旧配置路径：AstrBot/data/config/
        old_config_root = self.plugin_dir.parent.parent / "config"
        
        # 迁移 config.yaml
        old_config_path = old_config_root / "config.yaml"
        if old_config_path.exists() and not self.config_path.exists():
            try:
                import shutil
                shutil.copy2(old_config_path, self.config_path)
                logger.info(f"已迁移配置文件: {old_config_path} -> {self.config_path}")
            except Exception as exc:
                logger.warning(f"迁移配置文件失败: {exc}")
        
        # 迁移各平台的 whitelist.json
        for platform in ["aiocqhttp", "discord"]:
            old_whitelist_path = old_config_root / platform / "whitelist.json"
            new_platform_dir = self.data_dir / platform
            new_platform_dir.mkdir(parents=True, exist_ok=True)
            new_whitelist_path = new_platform_dir / "whitelist.json"
            
            if old_whitelist_path.exists() and not new_whitelist_path.exists():
                try:
                    import shutil
                    shutil.copy2(old_whitelist_path, new_whitelist_path)
                    logger.info(f"已迁移 {platform} 白名单: {old_whitelist_path} -> {new_whitelist_path}")
                except Exception as exc:
                    logger.warning(f"迁移 {platform} 白名单失败: {exc}")

    def _ensure_default_config(self) -> None:
        """确保配置文件存在，如果不存在则创建默认模板。"""
        default_preset_uc = "lowres, bad anatomy, bad hands, worst quality, jpeg artifacts"
        default_quality_words = "best quality, masterpiece"
        if not self.config_path.exists():
            content = DEFAULT_CONFIG_TEMPLATE.format(
                image_save_path=str((self.plugin_dir / "outputs").resolve()).replace("\\", "/"),
                preset_uc=default_preset_uc,
                quality_words=default_quality_words,
            )
            self.config_path.write_text(content, encoding="utf-8")
            logger.info(f"已创建默认配置文件: {self.config_path}")

    def _ensure_default_whitelists(self) -> None:
        """确保所有平台的 whitelist.json 文件存在，如果不存在则创建示例文件。"""
        # 支持的平台列表
        platforms = ["aiocqhttp", "discord"]
        
        # 示例 whitelist 数据
        example_whitelist = {
            "users": {
                "12345678": {
                    "daily_limit": 10,
                    "remaining": 10,
                    "last_reset": date.today().isoformat(),
                    "last_used_at": None,
                    "nickname": "示例用户"
                }
            },
            "groups": {
                "123456789": {
                    "name": "示例测试群"
                }
            }
        }
        
        for platform in platforms:
            platform_dir = self.data_dir / platform
            platform_dir.mkdir(parents=True, exist_ok=True)
            whitelist_path = platform_dir / "whitelist.json"
            
            if not whitelist_path.exists():
                # 对于 Discord 平台，不创建示例群组（因为 Discord 不使用群白名单）
                whitelist_data = example_whitelist.copy()
                if platform == "discord":
                    whitelist_data["groups"] = {}
                
                whitelist_path.write_text(
                    json.dumps(whitelist_data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                logger.info(f"已创建 {platform} 平台白名单示例文件: {whitelist_path}")

    def _get_platform_key(self, event: AstrMessageEvent) -> str:
        return event.get_platform_name().lower()

    def _get_platform_profile(self, event: AstrMessageEvent) -> PlatformProfile:
        key = self._get_platform_key(event)
        profile = self.platform_profiles.get(key)
        if profile:
            return profile

        # whitelist.json 放在插件文件夹的 data 目录下，按平台分目录
        platform_dir = self.data_dir / key
        platform_dir.mkdir(parents=True, exist_ok=True)
        whitelist_path = platform_dir / "whitelist.json"
        if not whitelist_path.exists():
            whitelist_path.write_text(
                json.dumps({"users": {}, "groups": {}}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        access_control = AccessControl(str(whitelist_path), self.config.default_daily_limit)
        use_group_whitelist = key not in {"discord"}
        profile = PlatformProfile(
            platform_name=key,
            access_control=access_control,
            whitelist_path=whitelist_path,
            use_group_whitelist=use_group_whitelist,
        )
        self.platform_profiles[key] = profile
        return profile

    def _fetch_discord_member_name(self, raw_message, user_id: str) -> Optional[str]:
        if raw_message is None:
            return None
        try:
            guild = getattr(raw_message, "guild", None)
            if guild is not None:
                member = guild.get_member(int(user_id))
                if member is not None:
                    return getattr(member, "display_name", None) or getattr(member, "name", None)
            mentions = getattr(raw_message, "mentions", []) or []
            for member in mentions:
                if str(member.id) == str(user_id):
                    return getattr(member, "display_name", None) or getattr(member, "name", None)
            author = getattr(raw_message, "author", None)
            if author and str(getattr(author, "id", None)) == str(user_id):
                return getattr(author, "display_name", None) or getattr(author, "name", None)
        except Exception:  # noqa: BLE001
            return None
        return None
