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


def process_image_by_orientation(image_source) -> Image.Image:
    """
    根据图片方向处理图片，调整为NovelAI API要求的尺寸。
    用于角色参考图片的预处理。
    
    Args:
        image_source: 图像路径(str)或PIL Image对象
        
    Returns:
        处理后的PIL Image对象
    """
    if isinstance(image_source, str):
        img = Image.open(image_source)
    elif isinstance(image_source, Image.Image):
        img = image_source.copy()
    else:
        raise ValueError("image_source must be str (path) or PIL Image")
    
    if img.mode != "RGB":
        img = img.convert("RGB")
    
    width, height = img.size
    
    if width > height:
        # 横图：调整为 1536x1024
        aspect_ratio = width / height
        target_aspect = 1536 / 1024
        if aspect_ratio > target_aspect:
            new_width = 1536
            new_height = int(height * (1536 / width))
            resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            final_img = Image.new("RGB", (1536, 1024), (0, 0, 0))
            y_offset = (1024 - new_height) // 2
            final_img.paste(resized_img, (0, y_offset))
        else:
            new_height = 1024
            new_width = int(width * (1024 / height))
            resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            final_img = Image.new("RGB", (1536, 1024), (0, 0, 0))
            x_offset = (1536 - new_width) // 2
            final_img.paste(resized_img, (x_offset, 0))
    elif height > width:
        # 竖图：调整为 1024x1536
        aspect_ratio = width / height
        target_aspect = 1024 / 1536
        if aspect_ratio > target_aspect:
            new_width = 1024
            new_height = int(height * (1024 / width))
            resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            final_img = Image.new("RGB", (1024, 1536), (0, 0, 0))
            y_offset = (1536 - new_height) // 2
            final_img.paste(resized_img, (0, y_offset))
        else:
            new_height = 1536
            new_width = int(width * (1536 / height))
            resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            final_img = Image.new("RGB", (1024, 1536), (0, 0, 0))
            x_offset = (1024 - new_width) // 2
            final_img.paste(resized_img, (x_offset, 0))
    else:
        # 方图：调整为 1472x1472
        final_img = img.resize((1472, 1472), Image.Resampling.LANCZOS)
    
    return final_img


def prepare_character_reference_image(image_source) -> str:
    """
    预处理角色参考图片，转换为base64。
    
    Args:
        image_source: 图像路径(str)或PIL Image对象
        
    Returns:
        Base64编码的字符串
    """
    processed_img = process_image_by_orientation(image_source)
    buffer = io.BytesIO()
    processed_img.save(buffer, format="PNG")
    img_bytes = buffer.getvalue()
    buffer.close()
    return base64.b64encode(img_bytes).decode("utf-8")


def prepare_base_image(image_source) -> str:
    """
    预处理底图，确保尺寸是64的倍数，转换为base64。
    
    Args:
        image_source: 图像路径(str)或PIL Image对象
        
    Returns:
        Base64编码的字符串
    """
    if isinstance(image_source, str):
        img = Image.open(image_source)
    elif isinstance(image_source, Image.Image):
        img = image_source.copy()
    else:
        raise ValueError("image_source must be str (path) or PIL Image")
    
    if img.mode != "RGB":
        img = img.convert("RGB")
    
    width, height = img.size
    # 调整为64的倍数
    new_width = (width // 64) * 64
    if new_width == 0:
        new_width = 64
    new_height = (height // 64) * 64
    if new_height == 0:
        new_height = 64
    
    if new_width != width or new_height != height:
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    img_bytes = buffer.getvalue()
    buffer.close()
    return base64.b64encode(img_bytes).decode("utf-8")


def extract_zip_image(zip_bytes: bytes, index: int = 0) -> bytes:
    """从NovelAI返回的ZIP数据中提取指定索引的图像。"""

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        image_name = f"image_{index}.png"
        if image_name not in zf.namelist():
            raise FileNotFoundError(f"ZIP中未找到{image_name}")
        with zf.open(image_name) as image_file:
            return image_file.read()

