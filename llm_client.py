"""大语言模型客户端抽象层。"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Optional

import aiohttp

from astrbot.api import logger


class LLMError(Exception):
    """LLM 调用错误。"""


class BaseLLMClient(ABC):
    """LLM 客户端抽象基类。"""

    @abstractmethod
    async def generate(self, prompt: str, timeout: int = 30) -> str:
        """
        生成文本响应。

        Args:
            prompt: 输入提示词
            timeout: 超时时间（秒）

        Returns:
            生成的文本响应

        Raises:
            LLMError: 调用失败时抛出
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """关闭客户端连接。"""
        pass


class OpenRouterLLMClient(BaseLLMClient):
    """OpenRouter API 客户端实现。
    
    根据 OpenRouter 官方文档实现，使用 OpenAI 兼容格式的 API。
    文档: https://openrouter.ai/docs
    """

    # OpenRouter API 基础 URL
    BASE_URL = "https://openrouter.ai/api/v1"
    # Chat completions 端点
    CHAT_COMPLETIONS_ENDPOINT = "/chat/completions"

    def __init__(
        self,
        api_key: str,
        models: list[str],
        proxy: Optional[str] = None,
        timeout: int = 30,
        http_referer: Optional[str] = None,
        x_title: Optional[str] = None,
    ) -> None:
        """
        初始化 OpenRouter 客户端。

        Args:
            api_key: OpenRouter API Key（必填，从 https://openrouter.ai 获取）
            models: 模型列表（按优先级排序，会依次尝试直到成功）
            proxy: HTTP 代理地址（可选）
            timeout: 默认超时时间（秒）
            http_referer: HTTP-Referer 头部（可选，用于在 openrouter.ai 上进行排名）
            x_title: X-Title 头部（可选，用于在 openrouter.ai 上进行排名）
        """
        if not api_key:
            raise LLMError("未配置 OpenRouter API Key")
        if not models:
            raise LLMError("未配置模型列表")
        self.api_key = api_key
        self.models = models
        self.proxy = proxy
        self.timeout = timeout
        # 设置可选的排名头部（根据 OpenRouter 文档）
        self.http_referer = http_referer or "https://github.com/astrbot/novelai-plugin"
        self.x_title = x_title or "NovelAI Plugin"
        self._session: Optional[aiohttp.ClientSession] = None
        self.last_used_model: Optional[str] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 HTTP 会话。"""
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector()
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
            )
        return self._session

    async def generate(self, prompt: str, timeout: Optional[int] = None) -> str:
        """
        调用 OpenRouter API 生成文本。

        根据 OpenRouter 官方文档实现：
        - 使用 POST 请求到 /chat/completions 端点
        - 请求体包含 model 和 messages（OpenAI 兼容格式）
        - 响应格式与 OpenAI API 兼容

        Args:
            prompt: 输入提示词
            timeout: 超时时间（秒），None 则使用默认值

        Returns:
            生成的文本响应

        Raises:
            LLMError: API 调用失败时抛出
        """
        if timeout is None:
            timeout = self.timeout

        session = await self._get_session()
        # 根据 OpenRouter 文档设置请求头
        # Authorization: Bearer token（必填）
        # HTTP-Referer 和 X-Title: 可选，用于在 openrouter.ai 上进行排名
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.http_referer,
            "X-Title": self.x_title,
        }

        # 构建完整的 API URL
        api_url = f"{self.BASE_URL}{self.CHAT_COMPLETIONS_ENDPOINT}"

        # 尝试每个模型，直到成功
        last_error: Optional[Exception] = None
        self.last_used_model = None
        for model in self.models:
            try:
                # 根据 OpenRouter 文档构建请求体（OpenAI 兼容格式）
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "user", "content": prompt},
                    ],
                }

                async with session.post(
                    api_url,
                    json=payload,
                    headers=headers,
                    proxy=self.proxy,
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        raise LLMError(
                            f"OpenRouter API 返回错误 (状态码 {resp.status}): {error_text[:200]}"
                        )

                    data = await resp.json()
                    # 检查响应中是否包含错误信息
                    if "error" in data:
                        error_info = data["error"]
                        if isinstance(error_info, dict):
                            error_msg = error_info.get("message", str(error_info))
                        else:
                            error_msg = str(error_info)
                        raise LLMError(f"OpenRouter API 错误: {error_msg}")

                    # 解析响应（OpenAI 兼容格式）
                    choices = data.get("choices", [])
                    if not choices:
                        raise LLMError("OpenRouter API 返回空响应")

                    # 提取消息内容
                    message = choices[0].get("message", {})
                    content = message.get("content", "")
                    if not content:
                        raise LLMError("OpenRouter API 返回空内容")

                    self.last_used_model = model
                    return content.strip()

            except asyncio.TimeoutError:
                last_error = LLMError(f"请求超时（模型: {model}）")
                logger.warning(f"模型 {model} 请求超时，尝试下一个模型")
                continue
            except aiohttp.ClientError as exc:
                last_error = LLMError(f"网络错误（模型: {model}）: {exc}")
                logger.warning(f"模型 {model} 网络错误: {exc}，尝试下一个模型")
                continue
            except LLMError as exc:
                # 如果是明确的 API 错误，直接抛出
                if "返回错误" in str(exc) or "API 错误" in str(exc):
                    raise
                last_error = exc
                logger.warning(f"模型 {model} 调用失败: {exc}，尝试下一个模型")
                continue

        # 所有模型都失败
        if last_error:
            raise last_error
        raise LLMError("所有模型调用均失败")

    async def close(self) -> None:
        """关闭 HTTP 会话。"""
        if self._session and not self._session.closed:
            await self._session.close()

