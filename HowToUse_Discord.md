# Discord 平台快速上手指南

本文档 **严格按照 `parser.py` 的解析规则** 撰写，帮助你在 Discord 上正确使用 `/nai` 与 `/nainl`。

---

## 1. 调用方式

1. **Slash 命令**：在聊天框输入 `/`，选择 `nai` 或 `nainl`，并只填写本文列出的字段。若表单出现其它字段，请保持默认或留空，否则会因“不存在的参数”而失败。
2. **纯文本输入**：直接发送 `/nai 参数名:<参数值>`。语法与 QQ 完全一致（必须带尖括号）。
3. **图片引用**：
   - **Slash 表单**：`底图` / `角色参考` 只提供 “是/否” 选项。选择 “是” 后，机器人会提示 “请发送底图/角色参考图”，并等待你在 60 秒内补发图片。由于无法同时上传两张图片，两个选项请不要同为 “是”，否则会提示报错。
   - **纯文本指令**（非 Slash）：依旧可以在同一条消息里附图，并用 `底图:<1>` / `角色参考:<2>` 指向第 n 张图片。
4. **白名单与限额**：账号需在白名单内且额度未耗尽，才能成功调用。额度每天 00:00 重置。

---

## 2. `/nai` 支持的字段（与 `parser.py` 完全一致）

### 2.1 基础参数

| Slash 字段 (文本别名) | 必填 | 取值范围 | 说明 |
| --- | --- | --- | --- |
| `prompt` (`正面词条`) | 是 | 任意提示词 | 缺失会报错。 |
| `negative_prompt` (`负面词条`) | 否 | 任意提示词 | 留空则使用 `preset_uc`（默认 Heavy）。 |
| `resolution` (`分辨率`) | 否 | `portrait/landscape/square` ↔ `竖图/横图/方图` | 只有这三种预设，**没有自定义宽高**。 |
| `steps` (`步数`) | 否 | 1~28 的整数 | 超出范围会被拒绝。 |
| `guidance` (`指导系数`) | 否 | 0~10 浮点 | 默认 5.0。 |
| `cfg_rescale` (`重采样系数`) | 否 | 0~1 浮点 | 默认 0.0。 |
| `seed` (`种子`) | 否 | -1 或整数 | -1/留空表示随机。 |
| `sampler` (`采样器`) | 否 | `k_euler、k_euler_ancestral、k_dpmpp_2s_ancestral、k_dpmpp_2m、k_dpmpp_sde、k_dpmpp_2m_sde` | 仅这些值有效。 |
| `model` (`模型`) | 否 | `MODELS` 列表中的任意项 | 例：`nai-diffusion-4-5-full`。 |
| `furry_mode` (`是否有福瑞`) | 否 | `true/false` 或 `是/否` | `True` 时会在提示词前追加 `fur dataset`。 |
| `add_quality_words` (`添加质量词`) | 否 | `true/false` | 控制是否附加 `quality_words`。 |
| `base_image` (`底图`) | 否 | Slash：`是/否`；纯文本：图片编号 | Slash 选 “是” 时会进入补图流程；纯文本仍可引用当前消息的图片序号。 |
| `base_image_strength` (`底图重绘强度`) | 否 | 0~1 浮点 | 默认 0.7（无论 Slash 还是纯文本）。 |
| `base_image_noise` (`底图加噪强度`) | 否 | 0~0.99 浮点 | 默认 0.0。 |
| `char_partition` (`角色是否分区`) | 否 | `true/false` | 未填写时根据角色数量自动决定。 |
| `char_reference` (`角色参考`) | 否 | Slash：`是/否`；纯文本：图片编号 | Slash 选 “是” 会触发补图流程，且与底图互斥；纯文本沿用图片序号写法。 |
| `char_reference_strength` (`角色参考强度`) | 否 | 0~1 浮点 | 默认 1.0。 |
| `style_aware` (`是否注意原画风`) | 否 | `true/false` | 默认为 False。 |

> ⚠️ Slash 模式的 `底图` 与 `角色参考` 不能同时为 “是”，否则插件会提示错误并终止本次请求。

> ⚠️ Slash UI 若显示 `Variety+`、`噪声调度`、`SMEA/DYN`、自定义宽高等字段，请不要填写——`parser.py` 不认识这些键，提交会直接报错 “未知参数”。

### 2.2 角色参数（最多 5 个）

| Slash 字段 (文本别名) | 取值 | 说明 |
| --- | --- | --- |
| `char{i}_prompt` (`角色{i}正面词条`) | 任意提示词 | 定义角色 i（1~5），**下面的参数务必与其一一对应**。 |
| `char{i}_negative` (`角色{i}负面词条`) | 任意提示词 | 可选。 |
| `char{i}_position` (`角色{i}位置`) | `A1~E5` | 不写则默认 `C3`。 |

只要设置了 `char{i}_prompt` 就视为启用该角色；索引超出 1~5 会抛错。

### 2.3 合法示例

```
/nai prompt:<masterpiece, 1girl, white dress>
     negative_prompt:<bad hands, extra fingers>
     resolution:<portrait> steps:<24> guidance:<6.0> cfg_rescale:<0.3>
     sampler:<k_dpmpp_2m> seed:<123456789>
     furry_mode:<false> add_quality_words:<true>
     base_image:<是> base_image_strength:<0.65> base_image_noise:<0.1>
     char1_prompt:<blue eyes, short hair> char1_negative:<open mouth> char1_position:<B2>
     style_aware:<true> model:<nai-diffusion-4-5-full>
```

> 上述示例在 Discord Slash 表单中选择 `底图=是`。发送指令后机器人会提示 “请发送底图”，你再补发图片即可。若使用纯文本并在消息中附图，则仍然可以写 `底图:<1>` 来引用序号。

若只写 `/nai prompt:<...>` 也没问题，其余字段自动使用默认值。

---

## 3. `/nainl` 自然语言模式

- Slash：只需填写 `text`（自然语言描述），其它字段请保持默认，否则会被忽略。
- 纯文本：`/nainl 夕阳下的蒸汽朋克城市`。
- 当前实现中，**所有结构化参数都会被丢弃**，仅自然语言描述会传给 LLM，再转为 `/nai 正面词条:<...>`。因此 `/nainl` 不支持自定义步骤、采样器等；想要细节控制请改用 `/nai`。

---

## 4. 管理与帮助指令

| 指令 | 说明 |
| --- | --- |
| `/nai_whitelist_add user:<成员> nickname:<可选>` | 添加/更新白名单。 |
| `/nai_whitelist_remove user:<成员>` | 移除白名单。 |
| `/nai_limit_set user:<成员> limit:<次数>` | 调整每日额度。 |
| `/naihelp` | 输出与 `parser.py` 一致的完整模板。 |

白名单文件保存在 `AstrBot/data/plugins/astrbot_plugin_novelai_img_generation/data/discord/whitelist.json`。

---

## 5. 常见问题

- **Slash 表单里的额外字段要填吗？** 不要。只填写本指南列出的字段，否则 `parser` 会拒绝。
- **提示 Unknown parameter**：说明填写了未在 `_GENERAL_KEYS` 或角色键列表里的字段。
- **角色提示无效**：必须为每个角色写 `char{i}_prompt`，位置只能是 `A1~E5`。
- **底图/角色参考引用失败**：Slash 模式请确认只勾选 “是”，并在 60 秒内补发图片；纯文本模式请确认消息里真的附带了对应编号的图片。
- **想在 `/nainl` 里改步数**：目前不支持，改用 `/nai`。

遵循以上规则即可在 Discord 上稳定绘图。若有新参数加入，请先确认 `parser.py` 更新后再写入指令。祝创作顺利！
