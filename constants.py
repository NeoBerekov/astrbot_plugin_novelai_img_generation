"""
NovelAI 常量定义
包含模型、采样器、预设等常量
"""

# 支持的模型列表
MODELS = [
    "nai-diffusion-4-5-full",
    "nai-diffusion-4-5-curated",
    "nai-diffusion-4-full",
    "nai-diffusion-4-curated-preview",
    "nai-diffusion-3",
    "nai-diffusion-furry-3",
]

# 采样器列表
SAMPLERS = [
    "k_euler",
    "k_euler_ancestral",
    "k_dpmpp_2s_ancestral",
    "k_dpmpp_2m",
    "k_dpmpp_sde",
    "k_dpmpp_2m_sde",
]

# 噪声调度
NOISE_SCHEDULES = ["native", "karras", "exponential", "polyexponential"]

# UC预设选项
UC_PRESETS = ["Heavy", "Light", "Furry Focus", "Human Focus", "None"]

# 分辨率映射
RESOLUTION_MAP = {
    "竖图": (832, 1216),
    "横图": (1216, 832),
    "方图": (1024, 1024),
}

# 角色位置映射 (A-E, 1-5)
CHARACTER_POSITIONS = [f"{chr(letter)}{number}" for letter in range(ord("A"), ord("F")) for number in range(1, 6)]


def position_to_float(position: str) -> tuple:
    """将位置字符串（如C3）转换为浮点坐标"""
    if not position or len(position) < 2:
        return (0.5, 0.5)  # 默认中心位置
    
    letter = position[0].upper()
    number = position[1]
    
    # 列映射 A-E -> 0.1, 0.3, 0.5, 0.7, 0.9
    col_map = {'A': 0.1, 'B': 0.3, 'C': 0.5, 'D': 0.7, 'E': 0.9}
    x = col_map.get(letter, 0.5)
    
    # 行映射 1-5 -> 0.1, 0.3, 0.5, 0.7, 0.9
    row_map = {'1': 0.1, '2': 0.3, '3': 0.5, '4': 0.7, '5': 0.9}
    y = row_map.get(number, 0.5)
    
    return (x, y)


def get_uc_preset_value(model: str, preset_name: str) -> int:
    """获取指定模型和预设名称的ucPreset值"""
    uc_preset_data = {
        "nai-diffusion-4-5-full": {
            "Heavy": 0,
            "Light": 1,
            "Furry Focus": 2,
            "Human Focus": 3,
            "None": 4,
        },
        "nai-diffusion-4-5-curated": {
            "Heavy": 0,
            "Light": 1,
            "Human Focus": 2,
            "None": 3,
        },
        "nai-diffusion-3": {
            "Heavy": 0,
            "Light": 1,
            "Human Focus": 2,
            "None": 3,
        },
        "nai-diffusion-furry-3": {
            "Heavy": 0,
            "Light": 1,
            "None": 2,
        },
        "nai-diffusion-4-curated-preview": {
            "Heavy": 0,
            "Light": 1,
            "None": 2,
        },
        "nai-diffusion-4-full": {
            "Heavy": 0,
            "Light": 1,
            "None": 2,
        },
    }
    
    return uc_preset_data.get(model, {}).get(preset_name, 0)


def get_quality_tags(model: str) -> str:
    """获取指定模型的质量标签"""
    quality_tags = {
        "nai-diffusion-4-5-full": ", very aesthetic, masterpiece, no text",
        "nai-diffusion-4-5-curated": ", very aesthetic, masterpiece, no text, -0.8::feet::, rating:general",
        "nai-diffusion-4-full": ", no text, best quality, very aesthetic, absurdres",
        "nai-diffusion-4-curated-preview": ", rating:general, best quality, very aesthetic, absurdres",
        "nai-diffusion-3": ", best quality, amazing quality, very aesthetic, absurdres",
        "nai-diffusion-furry-3": ", {best quality}, {amazing quality}",
    }
    return quality_tags.get(model, "")


def get_negative_preset(model: str, preset_name: str) -> str:
    """获取指定模型和预设名称的负面提示词"""
    presets = {
        "nai-diffusion-4-5-full": {
            "Heavy": "lowres, artistic error, film grain, scan artifacts, worst quality, bad quality, jpeg artifacts, very displeasing, chromatic aberration, dithering, halftone, screentone, multiple views, logo, too many watermarks, negative space, blank page",
            "Light": "lowres, artistic error, scan artifacts, worst quality, bad quality, jpeg artifacts, multiple views, very displeasing, too many watermarks, negative space, blank page",
            "Furry Focus": "{worst quality}, distracting watermark, unfinished, bad quality, {widescreen}, upscale, {sequence}, {{grandfathered content}}, blurred foreground, chromatic aberration, sketch, everyone, [sketch background], simple, [flat colors], ych (character), outline, multiple scenes, [[horror (theme)]], comic",
            "Human Focus": "lowres, artistic error, film grain, scan artifacts, worst quality, bad quality, jpeg artifacts, very displeasing, chromatic aberration, dithering, halftone, screentone, multiple views, logo, too many watermarks, negative space, blank page, @_@, mismatched pupils, glowing eyes, bad anatomy",
            "None": "",
        },
        "nai-diffusion-4-5-curated": {
            "Heavy": "blurry, lowres, upscaled, artistic error, film grain, scan artifacts, worst quality, bad quality, jpeg artifacts, very displeasing, chromatic aberration, halftone, multiple views, logo, too many watermarks, negative space, blank page",
            "Light": "blurry, lowres, upscaled, artistic error, scan artifacts, jpeg artifacts, logo, too many watermarks, negative space, blank page",
            "Human Focus": "blurry, lowres, upscaled, artistic error, film grain, scan artifacts, bad anatomy, bad hands, worst quality, bad quality, jpeg artifacts, very displeasing, chromatic aberration, halftone, multiple views, logo, too many watermarks, @_@, mismatched pupils, glowing eyes, negative space, blank page",
            "None": "",
        },
        "nai-diffusion-4-full": {
            "Heavy": "blurry, lowres, error, film grain, scan artifacts, worst quality, bad quality, jpeg artifacts, very displeasing, chromatic aberration, multiple views, logo, too many watermarks, white blank page, blank page",
            "Light": "blurry, lowres, error, worst quality, bad quality, jpeg artifacts, very displeasing, white blank page, blank page",
            "None": "",
        },
        "nai-diffusion-4-curated-preview": {
            "Heavy": "blurry, lowres, error, film grain, scan artifacts, worst quality, bad quality, jpeg artifacts, very displeasing, chromatic aberration, logo, dated, signature, multiple views, gigantic breasts, white blank page, blank page",
            "Light": "blurry, lowres, error, worst quality, bad quality, jpeg artifacts, very displeasing, logo, dated, signature, white blank page, blank page",
            "None": "",
        },
        "nai-diffusion-3": {
            "Heavy": "lowres, {bad}, error, fewer, extra, missing, worst quality, jpeg artifacts, bad quality, watermark, unfinished, displeasing, chromatic aberration, signature, extra digits, artistic error, username, scan, [abstract]",
            "Light": "lowres, jpeg artifacts, worst quality, watermark, blurry, very displeasing",
            "Human Focus": "lowres, {bad}, error, fewer, extra, missing, worst quality, jpeg artifacts, bad quality, watermark, unfinished, displeasing, chromatic aberration, signature, extra digits, artistic error, username, scan, [abstract], bad anatomy, bad hands, @_@, mismatched pupils, heart-shaped pupils, glowing eyes",
            "None": "lowres",
        },
        "nai-diffusion-furry-3": {
            "Heavy": "{{worst quality}}, [displeasing], {unusual pupils}, guide lines, {{unfinished}}, {bad}, url, artist name, {{tall image}}, mosaic, {sketch page}, comic panel, impact (font), [dated], {logo}, ych, {what}, {where is your god now}, {distorted text}, repeated text, {floating head}, {1994}, {widescreen}, absolutely everyone, sequence, {compression artifacts}, hard translated, {cropped}, {commissioner name}, unknown text, high contrast",
            "Light": "{worst quality}, guide lines, unfinished, bad, url, tall image, widescreen, compression artifacts, unknown text",
            "None": "lowres",
        },
    }
    return presets.get(model, {}).get(preset_name, "")


def get_skip_cfg_above_sigma(model: str) -> float:
    """获取指定模型的skip_cfg_above_sigma值"""
    sigma_values = {
        "nai-diffusion-4-5-full": 58.0,
        "nai-diffusion-4-5-curated": 36.158893609242725,
        "nai-diffusion-3": 11.84515480302779,
        "nai-diffusion-furry-3": 11.84515480302779,
        "nai-diffusion-4-curated-preview": 11.84515480302779,
        "nai-diffusion-4-full": 18.254609533779934,
    }
    return sigma_values.get(model, 0.0)

