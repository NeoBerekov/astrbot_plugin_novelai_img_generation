"""自然语言处理模块，将用户自然语言描述转换为 /nai 指令参数。"""

from __future__ import annotations

import re
from typing import Optional

from astrbot.api import logger

from .llm_client import BaseLLMClient, LLMError
from .parser import ParseError, parse_generation_message


class NLProcessingError(Exception):
    """自然语言处理错误。"""


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

    async def process(self, user_input: str) -> str:
        """
        处理用户自然语言输入，转换为 /nai 指令格式。

        Args:
            user_input: 用户输入的自然语言描述

        Returns:
            转换后的 /nai 指令文本

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
        except LLMError as exc:
            raise NLProcessingError(f"LLM 调用失败: {exc}") from exc

        # 步骤3: 解析 LLM 返回的参数
        parsed_text = self._extract_parameters(llm_response)

        # 步骤4: 验证解析结果
        try:
            # 尝试解析，验证格式是否正确
            parse_generation_message(f"/nai {parsed_text}")
        except ParseError as exc:
            logger.warning(f"LLM 返回的参数格式验证失败: {exc}，原始响应: {llm_response[:200]}")
            # 如果解析失败，尝试从响应中提取更干净的部分
            parsed_text = self._clean_extract(llm_response)
            # 再次验证
            try:
                parse_generation_message(f"/nai {parsed_text}")
            except ParseError:
                raise NLProcessingError(
                    f"LLM 返回的参数格式不正确，无法解析。原始响应: {llm_response[:300]}"
                ) from exc

        return parsed_text

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
            response = await self.llm_client.generate(prompt, timeout=15)
            response_lower = response.strip().lower()
            # 检查响应中是否包含"详细"
            return "详细" in response_lower or "detailed" in response_lower
        except LLMError as exc:
            logger.warning(f"详细度检查失败: {exc}，默认使用简单判断")
            # 失败时使用简单启发式
            words = user_input.split()
            return len(words) > 10 or len(user_input) > 50

    def _extract_parameters(self, llm_response: str) -> str:
        """
        从 LLM 响应中提取参数文本。

        Args:
            llm_response: LLM 原始响应

        Returns:
            提取的参数文本
        """
        # 尝试提取键值对格式的内容
        # 查找类似 "正面词条:<...>" 的模式
        pattern = r"(正面词条|负面词条|分辨率|步数|指导系数|采样器|模型|底图|底图重绘强度|底图加噪强度|是否有福瑞|添加质量词|角色是否分区|角色\d+正面词条|角色\d+负面词条|角色\d+位置|角色参考|角色参考强度|是否注意原画风|重采样系数|种子)[：:]\s*<[^>]*>"
        
        matches = re.findall(pattern, llm_response, re.IGNORECASE)
        if matches:
            # 如果找到匹配，尝试提取整个参数块
            lines = []
            for line in llm_response.split("\n"):
                line = line.strip()
                if re.search(pattern, line, re.IGNORECASE):
                    lines.append(line)
            if lines:
                return " ".join(lines)

        # 如果没有找到标准格式，尝试提取包含键值对的行
        lines = []
        for line in llm_response.split("\n"):
            line = line.strip()
            # 跳过空行和明显的解释性文字
            if not line or line.startswith("#") or line.startswith("//"):
                continue
            # 如果包含冒号和尖括号，可能是参数
            if ":" in line or "：" in line:
                if "<" in line and ">" in line:
                    lines.append(line)
                elif re.search(r"[：:]\s*\S+", line):
                    # 可能是没有尖括号的参数，尝试补充
                    lines.append(line)

        if lines:
            return " ".join(lines)

        # 如果都找不到，返回原始响应的前几行（去除明显的解释）
        cleaned_lines = []
        for line in llm_response.split("\n")[:10]:
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("//"):
                cleaned_lines.append(line)
        return " ".join(cleaned_lines)

    def _clean_extract(self, llm_response: str) -> str:
        """
        清理并提取参数文本（备用方法）。

        Args:
            llm_response: LLM 原始响应

        Returns:
            清理后的参数文本
        """
        # 移除常见的 LLM 解释性前缀
        prefixes_to_remove = [
            "以下是转换后的参数：",
            "转换后的参数如下：",
            "根据您的要求，",
            "Here are the converted parameters:",
            "The converted parameters are:",
        ]

        cleaned = llm_response
        for prefix in prefixes_to_remove:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()

        # 提取所有包含键值对的行
        lines = []
        for line in cleaned.split("\n"):
            line = line.strip()
            if not line:
                continue
            # 跳过明显的解释性文字
            if any(
                skip in line.lower()
                for skip in ["要求", "要求", "注意", "note", "requirement", "please"]
            ):
                if "正面词条" not in line and "positive" not in line.lower():
                    continue
            lines.append(line)

        return " ".join(lines)

