# NovelAI 图片生成插件

`astrbot_plugin_novelai_img_generation` 是基于 AstraBot 的 NovelAI 官方 API 图片生成插件，支持文本/图生图、角色定位、参考图等高级参数，并提供完善的权限与限流控制，适用于 QQ 群聊与私聊场景。

## 功能总览

- `/nai` 指令发起图片生成，支持中文/英文冒号的 `Key:<Value>` 参数格式。
- **`/nainl` 自然语言生图**：支持任意语言的自然语言描述，自动转换为标准参数格式。
- 参数解析内建默认值、范围校验与角色定位、福瑞等高级开关。
- 支持底图（Image2Image）、角色参考、角色分区（最多 5 角色）。
- 请求进入异步队列顺序执行，每次生成之间随机延迟 3~5 秒。
- 用户白名单 + 每日限额控制，数据持久化于插件目录下的 `data/{platform}/whitelist.json`。
- **群白名单**：仅白名单群 + 白名单用户 + 群内 @ 机器人时才响应，私聊不受影响。
- `/nai插件重启` 支持热加载 `config.yaml`，无需重启 AstraBot。

## 使用

根据部署平台选择参考对应说明：

- QQ 平台说明：`HowToUse_QQ.md`
- Discord 平台说明：`HowToUse_Discord.md`

它们分别介绍 Slash 命令、参数格式、白名单操作等细节，便于不同平台的用户快速上手。

## 安装与配置

1. 安装依赖：

   ```bash
   pip install -r AstrBot/data/plugins/astrbot_plugin_novelai_img_generation/requirements.txt
   ```

2. 首次运行插件若检测不到配置文件，会自动在插件目录生成模板；也可手动编辑：

   `AstrBot/data/plugins/astrbot_plugin_novelai_img_generation/config.yaml`

   ```yaml
   # NovelAI 插件配置模板
   nai_token: "your_novelai_token"
   proxy: "http://127.0.0.1:7890"      # 可选
   default_model: "nai-diffusion-4-5-curated"
   image_save_path: "C:/Absolute/Path/To/astrbot_plugin_novelai_img_generation/outputs"
   preset_uc: "lowres, bad anatomy, bad hands, worst quality, jpeg artifacts"
   quality_words: "best quality, masterpiece"
   default_daily_limit: 10
   admin_qq_list:
     - "12345678"
   ```

   - `nai_token`：NovelAI 官网获取的 Bearer Token。
   - `proxy`：可选代理，留空则直连。
   - `default_model`：默认生成模型，可被指令覆盖。
   - `image_save_path`：生成结果保存路径（必须为绝对路径）。
   - `preset_uc`：当指令里未填写“负面词条”时，使用的默认负面提示词；留空则回退到内置 Heavy 预设。
   - `quality_words`：当主提示词中缺少 `best quality` 或 `masterpiece` 时自动追加的质量词列表。
   - `admin_qq_list`：可执行管理命令的 QQ 号。
   - `nl_settings`：自然语言处理设置（可选，用于启用 `/nainl` 功能），详见下方说明。

3. 插件同样会在缺少文件时自动创建各平台的白名单文件；你也可以预置内容，结构如下：
   - QQ 平台：`AstrBot/data/plugins/astrbot_plugin_novelai_img_generation/data/aiocqhttp/whitelist.json`
   - Discord 平台：`AstrBot/data/plugins/astrbot_plugin_novelai_img_generation/data/discord/whitelist.json`

   ```json
   {
     "users": {
       "12345678": {
         "daily_limit": 10,
         "remaining": 10,
         "last_reset": "2025-11-07",
         "last_used_at": null,
         "nickname": "示例用户"
       }
     },
     "groups": {
       "123456789": {
         "name": "示例测试群"
       }
     }
   }
   ```

   群白名单为空时，群聊中的 `/nai` 请求将全部忽略。

## 指令 `/nai`

在群聊需先 `@机器人`，并保证群号与发起者都在白名单；私聊无须 @。

示例：

```
+/nai 正面词条:<masterpiece, best quality> 负面词条:<lowres> 分辨率:<竖图>
     步数:<24> 是否有福瑞:<否>
```

要点：

- 支持 `Key:<Value>` 与 `Key：<Value>`（中文冒号）。
- 参数间可用空格或换行分隔，值必须放在尖括号中。
- 若消息携带多张图片，可用顺序编号引用，如 `底图:<1>`。
- 插件检测参数合法性并给出默认值；解析失败将返回具体错误（私聊可见）。

### 支持参数一览

| 参数 | 说明 | 默认值 / 限制 |
| --- | --- | --- |
| 正面词条 | **必填**，NovelAI 提示词 | 无默认，缺失报错 |
| 负面词条 | NovelAI 负面提示词 | Heavy 预设 |
| 是否有福瑞 | `是/否`，为“是”时自动添加 `fur dataset` | 否 |
| 添加质量词 | `是/否`，附加模型质量标签 | 否 |
| 底图 | 图生图参考图（序号） | 空 |
| 底图重绘强度 | 0~1 | 0.7 |
| 底图加噪强度 | 0~0.99 | 0 |
| 分辨率 | `竖图/横图/方图` | 竖图（832x1216） |
| 步数 | ≤28 的整数 | 28 |
| 指导系数 | 0~10 | 5 |
| 重采样系数 | 0~1 | 0 |
| 种子 | 整数；缺省随机 | 随机 |
| 采样器 | `k_euler`、`k_dpmpp_2m` 等 | `k_euler_ancestral` |
| 角色是否分区 | `是/否`，开启角色定位 | 若 ≤1 角色则强制否 |
| 角色{n}正面词条 | 角色提示词（最多 5 角色） | - |
| 角色{n}负面词条 | 角色负面提示词 | 空 |
| 角色{n}位置 | A1~E5 网格坐标 | 默认 C3 |
| 角色参考 | 参考图序号 | 空（若有底图则忽略） |
| 角色参考强度 | 0~1 | 1 |
| 是否注意原画风 | `是/否` | 否 |
| 模型 | 可覆盖默认模型 | `config.yaml` 中设置 |

## 指令 `/nainl`（自然语言生图）

`/nainl` 允许用户使用自然语言描述图像需求，插件会自动调用大语言模型（LLM）将描述转换为标准的 `/nai` 参数格式，然后复用现有的生图流程。

### 功能特点

- **多语言支持**：支持任意语言的自然语言输入（中文、英文、日文等）。
- **智能判断**：自动判断描述详细度，选择“扩写”或“翻译扩展”模板。
- **配置覆盖**：支持为 `/nainl` 单独配置质量词和负面词条覆盖。
- **可扩展架构**：LLM 客户端采用抽象接口设计，便于后续接入其他 API 供应商。

### 配置要求

在 `config.yaml` 中添加 `nl_settings` 配置节（用于启用 `/nainl` 功能）：

```yaml
nl_settings:
  # 质量词覆盖（为空则使用全局 quality_words）
  quality_words_override: ""
  # 负面词条覆盖（为空则使用全局 preset_uc）
  negative_preset_override: ""
  # LLM 提供商，目前支持 openrouter
  llm_provider: "openrouter"
  # OpenRouter API 配置
  openrouter:
    # API Key（必填，从 https://openrouter.ai 获取）
    api_key: "your_openrouter_api_key"
    # 使用的模型列表（按优先级排序，会依次尝试）
    models:
      - "openai/gpt-4o-mini"
      - "anthropic/claude-3-haiku"
    # API 超时时间（秒）
    timeout: 30
  # 提示词模板（可选，使用默认模板时可省略）
  prompt_templates:
    detail_check: |
      请判断以下用户描述是否足够详细...
    expand: |
      你是一个专业的AI图像生成提示词助手...
    translate: |
      你是一个专业的AI图像生成提示词助手...
```

### 使用示例

```
/nainl 一个穿着蓝色连衣裙的长发少女，站在樱花树下，阳光透过树叶洒在她身上
```

插件会：
1. 调用 LLM 判断描述详细度
2. 根据详细度选择模板（扩写或翻译扩展）
3. 将自然语言转换为标准参数格式
4. 应用配置的质量词/负面词条覆盖（如果有）
5. 复用 `/nai` 的生图流程

### 注意事项

- `/nainl` 功能需要正确配置 `nl_settings` 才能使用，否则会提示功能未启用。
- LLM API 调用会产生额外费用，请根据 OpenRouter 的定价合理使用。
- 如果 LLM 返回的参数格式不正确，插件会尝试清理提取，失败时会返回错误信息。
- 配置修改后需要执行 `/nai插件重启` 才能生效。

## 管理命令一览

仅管理员（私聊或在白名单群内）可用。

### 用户白名单
- `/nai白名单 添加 <QQ|@某人> [昵称]`
- `/nai白名单 删除 <QQ|@某人>`
- `/nai限额 设置 <QQ|@某人> <次数> [昵称]`

命令会自动解析消息中的 `@` 或 `昵称(QQ)` 形式，并存储昵称。

### 群白名单
- `/nai群白名单 添加 [群号|本群] [群名称]`
  - 在目标群内直接使用 `本群` 可自动抓取群号与群名。
- `/nai群白名单 删除 [群号|本群]`

只有当群号与发起者都在白名单时，并且消息中真正 @ 了机器人，群聊请求才会被处理；未满足条件时插件完全静默。

### 软重启
- `/nai插件重启`
  - 重新载入 `config.yaml`，刷新默认模型、限额、管理员等配置。

## 队列与限额机制

- 所有请求进入异步队列；插入 3~5 秒随机延迟，降低 NovelAI 限流风险。
- 每日限额随系统日期变化自动重置；也可以手动通过命令调整。
- 队列处理成功后会 @ 调用者并附图返回；失败则在同会话中回复错误。

## 私聊支持

私聊中 `/nai` 指令不受群白名单限制，仍然需要用户在白名单且额度充足。参数校验、队列处理流程与群聊一致。

## 常见问题

- **没有响应**：确认群号已在白名单内、用户也在白名单、消息里确实 @ 了机器人。
- **提示缺少 `/nai`**：群聊需在 @ 后紧接 `/nai` 指令；私聊直接输入即可。
- **参数解析失败**：确保 `Key:<Value>` 或 `Key：<Value>`，并在尖括号内填写内容。
- **修改配置未生效**：执行 `/nai插件重启`，或重启整个平台。

如需进一步定制（例如扩展参数、其他平台支持），欢迎根据源码自行扩展。祝使用愉快！
