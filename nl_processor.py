"""自然语言处理模块，将用户自然语言描述转换为 /nai 指令参数。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from astrbot.api import logger

from .llm_client import BaseLLMClient, LLMError
from .parser import ParseError, parse_generation_message


class NLProcessingError(Exception):
    """自然语言处理错误。"""


@dataclass
class NLProcessResult:
    """自然语言处理结果。"""

    params_text: str
    model_name: Optional[str] = None


class NLProcessor:
    """自然语言处理器。"""

    def __init__(
        self,
        llm_client: BaseLLMClient,
        prompt_templates: dict[str, str],
    ) -> None:
        """
        初始化自然语言处理器。

        Args:
            llm_client: LLM 客户端实例
            prompt_templates: 提示词模板字典，包含 detail_check、expand、translate
        """
        self.llm_client = llm_client
        self.prompt_templates = prompt_templates

    async def process(
        self,
        user_input: str,
        auto_add_quality_words: bool = True,
        quality_words: str = "",
    ) -> NLProcessResult:
        """
        处理用户自然语言输入，转换为 /nai 指令格式。

        Args:
            user_input: 用户输入的自然语言描述
            auto_add_quality_words: 是否自动添加质量词，默认为 True
            quality_words: 质量词内容，当 auto_add_quality_words 为 True 时使用

        Returns:
            转换后的 /nai 指令结果，包含参数文本和使用的模型名称

        Raises:
            NLProcessingError: 处理失败时抛出
        """
        if not user_input.strip():
            raise NLProcessingError("输入不能为空")

        # 步骤1: 判断描述详细度
        is_detailed = await self._check_detail(user_input)

        # 步骤2: 根据详细度选择模板并调用 LLM
        if is_detailed:
            template_key = "expand"
            logger.debug("用户描述较详细，使用扩写模板")
        else:
            template_key = "translate"
            logger.debug("用户描述较简单，使用翻译扩展模板")

        template = self.prompt_templates.get(template_key)
        if not template:
            raise NLProcessingError(f"缺少模板: {template_key}")

        # 渲染模板
        prompt = template.format(user_input=user_input)

        # 调用 LLM
        try:
            llm_response = await self.llm_client.generate(prompt)
            print(f"LLM 响应: {llm_response}")
        except LLMError as exc:
            raise NLProcessingError(f"LLM 调用失败: {exc}") from exc

        # 步骤3: 清理并提取正面词条
        # LLM 现在只返回英文提示词文本，我们需要将其包装成 "正面词条:<...>" 格式
        positive_prompt = self._extract_positive_prompt(llm_response)

        # 步骤4: 根据 auto_add_quality_words 决定是否添加质量词
        if auto_add_quality_words and quality_words:
            quality_words_clean = quality_words.strip().strip(",")
            if quality_words_clean:
                # 检查是否已包含质量词
                if "best quality" not in positive_prompt.lower() and "masterpiece" not in positive_prompt.lower():
                    # 在正面词条后附加质量词
                    positive_prompt = f"{positive_prompt}, {quality_words_clean}"

        # 步骤5: 构建参数格式
        # 只返回正面词条，其他参数使用默认值或由配置覆盖
        parsed_text = f"正面词条:<{positive_prompt}>"

        # 步骤6: 验证解析结果
        try:
            parse_generation_message(f"/nai {parsed_text}")
        except ParseError as exc:
            raise NLProcessingError(
                f"生成的参数格式验证失败: {exc}，正面词条: {positive_prompt[:200]}"
            ) from exc

        model_name = getattr(self.llm_client, "last_used_model", None)

        return NLProcessResult(params_text=parsed_text, model_name=model_name)

    async def _check_detail(self, user_input: str) -> bool:
        """
        判断用户描述是否详细。

        Args:
            user_input: 用户输入

        Returns:
            True 表示详细，False 表示不详细
        """
        template = self.prompt_templates.get("detail_check")
        if not template:
            # 如果没有详细度检查模板，默认使用简单启发式判断
            # 如果输入长度较短或关键词较少，认为不详细
            words = user_input.split()
            return len(words) > 10 or len(user_input) > 50

        prompt = template.format(user_input=user_input)
        try:
            llm_timeout = getattr(self.llm_client, "timeout", None)
            response = await self.llm_client.generate(prompt, timeout=llm_timeout)
            print(f"详细度检查响应: {response}")
            response_lower = response.strip().lower()
            print(f"详细度检查响应小写: {response_lower}")
            # 检查响应中是否包含"详细"
            return "详细" in response_lower or "detailed" in response_lower
        except LLMError as exc:
            logger.warning(f"详细度检查失败: {exc}，默认使用简单判断")
            # 失败时使用简单启发式
            words = user_input.split()
            return len(words) > 10 or len(user_input) > 50

    def _extract_positive_prompt(self, llm_response: str) -> str:
        """
        从 LLM 响应中提取正面词条（英文提示词）。

        Args:
            llm_response: LLM 原始响应（应该只包含英文提示词文本）

        Returns:
            清理后的正面词条文本
        """
        # 移除常见的 LLM 解释性前缀和后缀
        prefixes_to_remove = [
            "以下是转换后的提示词：",
            "转换后的提示词如下：",
            "根据您的要求，",
            "Here is the converted prompt:",
            "The converted prompt is:",
            "正面词条:",
            "正面词条：",
            "Positive prompt:",
            "Prompt:",
        ]
        
        suffixes_to_remove = [
            "。",
            ".",
            "以上是转换后的提示词。",
            "This is the converted prompt.",
        ]

        cleaned = llm_response.strip()
        
        # 移除前缀
        for prefix in prefixes_to_remove:
            if cleaned.lower().startswith(prefix.lower()):
                cleaned = cleaned[len(prefix):].strip()
        
        # 移除后缀
        for suffix in suffixes_to_remove:
            if cleaned.lower().endswith(suffix.lower()):
                cleaned = cleaned[:-len(suffix)].strip()
        
        # 如果响应中包含 "正面词条:<...>" 格式，提取其中的内容
        pattern = r"正面词条[：:]\s*<([^>]+)>"
        match = re.search(pattern, cleaned, re.IGNORECASE)
        if match:
            cleaned = match.group(1).strip()
        
        # 如果响应中包含 "Positive prompt: ..." 格式，提取其中的内容
        pattern = r"positive\s*prompt[：:]\s*(.+)"
        match = re.search(pattern, cleaned, re.IGNORECASE)
        if match:
            cleaned = match.group(1).strip()
        
        # 移除多余的引号
        cleaned = cleaned.strip('"').strip("'").strip()
        
        # 如果响应是多行的，尝试提取主要内容（跳过明显的解释性文字）
        lines = []
        for line in cleaned.split("\n"):
            line = line.strip()
            if not line:
                continue
            # 跳过明显的解释性文字
            skip_keywords = [
                "要求", "requirement", "note", "注意", "please",
                "用户描述", "user input", "description",
            ]
            if any(keyword.lower() in line.lower() for keyword in skip_keywords):
                # 但如果这行包含实际的提示词内容，保留它
                if not any(char.isalpha() for char in line):
                    continue
            lines.append(line)
        
        if lines:
            cleaned = " ".join(lines)
        
        # 最终清理：移除多余的空格
        cleaned = " ".join(cleaned.split())
        
        if not cleaned:
            raise NLProcessingError("无法从 LLM 响应中提取有效的正面词条")
        
        return cleaned

