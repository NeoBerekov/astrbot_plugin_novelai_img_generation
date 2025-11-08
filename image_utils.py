"""图像处理工具函数。"""

import base64
import io
import zipfile
from typing import Optional

from PIL import Image


def image_to_base64(image_source) -> str:
    """
    将图像转换为Base64编码
    
    Args:
        image_source: 图像路径(str)或字节数据(bytes)
        
    Returns:
        Base64编码的字符串
    """
    if isinstance(image_source, str):
        # 从文件路径读取
        with Image.open(image_source) as img:
            if img.mode != "RGB":
                img = img.convert("RGB")
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            img_bytes = buffer.getvalue()
    elif isinstance(image_source, bytes):
        # 直接使用字节数据
        img_bytes = image_source
    else:
        raise ValueError("image_source must be str (path) or bytes")
    
    return base64.b64encode(img_bytes).decode("utf-8")


def base64_to_image(base64_str: str) -> bytes:
    """
    将Base64编码转换为图像字节数据
    
    Args:
        base64_str: Base64编码的字符串
        
    Returns:
        图像字节数据
    """
    return base64.b64decode(base64_str)


def resize_image_to_multiple_of_64(
    image_path: str,
    target_width: Optional[int] = None,
    target_height: Optional[int] = None,
) -> Image.Image:
    """
    调整图像尺寸为64的倍数
    
    Args:
        image_path: 图像路径
        target_width: 目标宽度（可选）
        target_height: 目标高度（可选）
        
    Returns:
        调整后的PIL Image对象
    """
    with Image.open(image_path) as img:
        if img.mode != "RGB":
            img = img.convert("RGB")
        
        width, height = img.size
        
        # 如果没有指定目标尺寸，调整为当前尺寸最接近的64的倍数
        if target_width is None:
            target_width = (width // 64) * 64
            if target_width == 0:
                target_width = 64
        
        if target_height is None:
            target_height = (height // 64) * 64
            if target_height == 0:
                target_height = 64
        
        # 使用高质量重采样
        resized_img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
        return resized_img


def ensure_multiple_of_64(value: int) -> int:
    """
    确保数值是64的倍数
    
    Args:
        value: 输入值
        
    Returns:
        调整后的值（64的倍数）
    """
    result = (value // 64) * 64
    if result == 0:
        result = 64
    return result


def save_image_from_bytes(image_bytes: bytes, save_path: str) -> None:
    """
    将图像字节数据保存为文件
    
    Args:
        image_bytes: 图像字节数据
        save_path: 保存路径
    """
    with open(save_path, "wb") as f:
        f.write(image_bytes)


def load_image_as_base64(image_path: str) -> str:
    """
    加载图像文件并转换为Base64
    
    Args:
        image_path: 图像文件路径
        
    Returns:
        Base64编码的字符串
    """
    return image_to_base64(image_path)


def extract_zip_image(zip_bytes: bytes, index: int = 0) -> bytes:
    """从NovelAI返回的ZIP数据中提取指定索引的图像。"""

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        image_name = f"image_{index}.png"
        if image_name not in zf.namelist():
            raise FileNotFoundError(f"ZIP中未找到{image_name}")
        with zf.open(image_name) as image_file:
            return image_file.read()

