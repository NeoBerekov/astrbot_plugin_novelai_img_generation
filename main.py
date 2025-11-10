"""NovelAI 图片生成插件主入口。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
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
from .nai_api import NovelAIAPI, NovelAIAPIError
from .parser import ParseError, ParsedParams, parse_generation_message
from .queue_manager import RequestQueue

DEFAULT_CONFIG_TEMPLATE = """# NovelAI 插件配置模板\n\n# NovelAI API访问Token，登陆NovelAI后抓取。\nnai_token: ""\n\n# HTTP代理，可选。如需走代理，填写例如 http://127.0.0.1:7890\nproxy: ""\n\n# 默认模型，可选值：\n# - nai-diffusion-4-5-full\n# - nai-diffusion-4-5-curated\n# - nai-diffusion-4-full\n# - nai-diffusion-4-curated-preview\n# - nai-diffusion-3\n# - nai-diffusion-furry-3\ndefault_model: "nai-diffusion-4-5-curated"\n\n# 图像保存路径，使用绝对路径\nimage_save_path: "{image_save_path}"\n\n# 负面词条预设（未填写“负面词条”时使用）\npreset_uc: "{preset_uc}"\n\n# 质量词，未检测到 best quality 与 masterpiece 时自动追加\nquality_words: "{quality_words}"\n\n# 默认每日调用次数上限（白名单用户可单独配置）。\ndefault_daily_limit: 10\n\n# 管理员QQ号列表，可在运行时通过命令动态调整。\nadmin_qq_list: []\n"""


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
        self.data_root = Path(__file__).resolve().parents[2]
        self.config_dir = self.data_root / "config"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.config_dir / "config.yaml"
        self._ensure_default_config()
        self.config = self._load_config()
        self.platform_profiles: dict[str, PlatformProfile] = {}
        self.nai_api: Optional[NovelAIAPI] = None
        self._init_error: Optional[str] = None
        self._init_nai_api()
        self.request_queue = RequestQueue(self._process_queue_item)

    async def initialize(self):
        await self.request_queue.start()

    async def terminate(self):
        await self.request_queue.stop()
        if self.nai_api:
            await self.nai_api.close()

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
        return PluginConfig(
            nai_token=str(merged.get("nai_token", "")),
            proxy=merged.get("proxy") or None,
            default_model=default_model,
            image_save_path=str(image_path),
            default_daily_limit=int(merged.get("default_daily_limit", 10)),
            admin_qq_list=[str(x) for x in merged.get("admin_qq_list", [])],
            preset_uc=str(merged.get("preset_uc", "") or ""),
            quality_words=str(merged.get("quality_words", "") or ""),
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
            chain.chain.append(Plain(f"图片生成完成！模型: {model}，种子: {seed}"))
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

    async def _reset_api(self):
        if self.nai_api:
            await self.nai_api.close()
        self._init_nai_api()

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
        if self._init_error:
            return False, f"配置重载完成，但 NovelAI 初始化失败：{self._init_error}"
        return True, "插件配置已重新加载"

    def _ensure_default_config(self) -> None:
        default_preset_uc = "lowres, bad anatomy, bad hands, worst quality, jpeg artifacts"
        default_quality_words = "best quality, masterpiece"
        if not self.config_path.exists():
            content = DEFAULT_CONFIG_TEMPLATE.format(
                image_save_path=str((self.plugin_dir / "outputs").resolve()).replace("\\", "/"),
                preset_uc=default_preset_uc,
                quality_words=default_quality_words,
            )
            self.config_path.write_text(content, encoding="utf-8")

    def _get_platform_key(self, event: AstrMessageEvent) -> str:
        return event.get_platform_name().lower()

    def _get_platform_profile(self, event: AstrMessageEvent) -> PlatformProfile:
        key = self._get_platform_key(event)
        profile = self.platform_profiles.get(key)
        if profile:
            return profile

        platform_dir = self.config_dir / key
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
