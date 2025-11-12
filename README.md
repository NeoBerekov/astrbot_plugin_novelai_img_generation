# NovelAI 图片生成插件

`astrbot_plugin_novelai_img_generation` 是基于 AstraBot 的 NovelAI 官方 API 插件，现已支持文本指令、自然语言转写、角色分区、参考图、质量词自动补全等高级能力，并内置完善的白名单与限流体系，可同时部署在 QQ 与 Discord。

## 核心特性

- `/nai` 指令解析 `Key:<Value>` / `Key：<Value>` 参数，自动补空缺项（质量词、负面词条、默认模型等）。
- `/nainl` 自然语言模式：自动调用 OpenRouter LLM，先判断描述详细度，再扩写/翻译生成标准提示词；支持多语言、角色出处检索、质量词与负面词条覆盖。
- 未检测到任何键值对时，会提示“全文作为正面词条”并照常生成。
- 队列串行处理 + 3~5 秒随机延迟，降低 NovelAI 官方限流风险。
- 针对 QQ / Discord 划分独立的用户白名单、每日限额、数据存储目录；群白名单仅在 QQ 生效。
- `/nai插件重启` 热加载配置文件，无需重启 AstraBot。
- `/naihelp` 提供完整参数模板，便于用户复制填写。

更多面向终端用户的说明，请分别查看 `HowToUse_QQ.md` 与 `HowToUse_Discord.md`。

## 快速上手

### 1. 安装依赖

```bash
pip install -r AstrBot/data/plugins/astrbot_plugin_novelai_img_generation/requirements.txt
```

### 2. 启动

- 直接运行 `AstrBot/start_astrbot.bat`（自动激活 `astrbot` 环境并执行 `uv run main.py`）。
- 首次加载插件时，会在 `AstrBot/data/plugins/astrbot_plugin_novelai_img_generation/` 下自动生成 `config.yaml` 及各平台白名单模板。

### 3. 配置 `config.yaml`

示例（默认模板片段）：

```yaml
nai_token: "your_novelai_token"
proxy: "http://127.0.0.1:7890"
default_model: "nai-diffusion-4-5-curated"
image_save_path: "D:/NovelaiOutputs"
preset_uc: "lowres, bad anatomy, bad hands, worst quality, jpeg artifacts"
quality_words: "best quality, masterpiece"
default_daily_limit: 10
admin_qq_list: []

nl_settings:
  quality_words_override: ""
  negative_preset_override: ""
  llm_provider: "openrouter"
  openrouter:
    api_key: "sk-..."
    models:
      - "openai/gpt-5-mini:online"
      - "moonshotai/kimi-k2-thinking:online"
      - "openai/gpt-4o-mini:online"
    timeout: 120
    http_referer: ""
    x_title: ""
```

> **提示**：
> - `image_save_path` 必须是绝对路径，插件会在其中按日期保存图片。
> - `admin_qq_list` 为可以执行管理命令的账号；Discord 上仍需手动赋权 Slash 命令。
> - `nl_settings` 为空则 `/nainl` 功能禁用；填写后自动注册并启用自然语言模式。

### 4. 白名单文件

- QQ：`data/aiocqhttp/whitelist.json`
- Discord：`data/discord/whitelist.json`

结构示例：

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
      "name": "示例群"
    }
  }
}
```

缺失文件会在启动时自动补齐。

## 指令速览

| 指令 | 适用平台 | 说明 |
| --- | --- | --- |
| `/nai ...` | QQ / Discord | 标准文本参数接口。QQ 群聊无需再 @ 机器人。 |
| `/nainl ...` | QQ / Discord | 自然语言转标准提示词；发送后会提示“自然语言交由 LLM 分析中，请稍后~”。 |
| `/naihelp` | QQ / Discord | 返回完整参数模板与说明。 |
| `/nai白名单 添加/删除/限额` | QQ（中文） | 用户白名单与限额管理。 |
| `/nai群白名单 ...` | QQ | 群白名单管理。被删除或未授权的群请求将完全静默。 |
| `/nai_whitelist_add` / `/nai_whitelist_remove` | Discord | Slash 形式的白名单管理。 |
| `/nai插件重启` | QQ / Discord | 重新读取 `config.yaml` 与白名单。 |

## 指令细节

### `/nai`

- 支持所有 `Key:<Value>` / `Key：<Value>` 格式；如未写任何键值对，会提示“将全文视作正面词条”。
- 自动补充质量词：若主提示词缺少 `best quality` 和 `masterpiece`，会追加 `config.yaml` 中的 `quality_words`。
- 负面词条缺省时使用 `preset_uc`；若配置也为空，则回退到内置 Heavy 预设。
- 角色（最多 5 位）可指定正负面词条、位置（A1~E5）、参考图与权重。
- 底图与角色参考均引用消息内图片顺序编号。
- `/naihelp` 会输出所有参数说明，方便复制粘贴。

### `/nainl`

工作流程：

1. 输出“自然语言交由 LLM 分析中，请稍后~”。
2. 调用 LLM 判断描述是否详细（超时使用 `nl_settings.openrouter.timeout`）。
3. 详细描述走“扩写模板”，简要描述走“翻译扩展模板”。
4. 模板会先识别有无作品出处的角色名：若存在，将自动查询官方英文名及 danbooru 标准 tag，并在提示词中使用标准写法。
5. 生成的正面词条会再检查质量词、负面词条是否需要覆盖。
6. 最终参数走与 `/nai` 一致的流程，并在完成时提示使用了哪一个 LLM 模型。

参数补充：

- 可额外写 `是否自动添加质量词:<否>` 切换质量词补全策略。
- 当自然语言中提供了键值对（如 `正面词条:<...>`），仍然会先交由 LLM 重新生成标准提示词。

## 队列、限额与输出

- 所有请求进入队列按序执行，每次加入 3~5 秒随机延迟。
- 每个用户每天有独立计数，跨平台互不影响；管理员可随时调整剩余额度。
- 生成成功后会将图片保存到 `image_save_path/{date}/`，并在会话中附带模型、种子与 LLM 名称。

## 常见问题

- **没有响应（QQ）**：确认用户和群都在白名单，且没有触发每日上限；插件现在无需 @ 机器人，直接输入 `/nai` 或 `/nainl` 即可。
- **Discord Slash 命令未出现**：重新邀请或赋予 `applications.commands` 权限，再执行一次 `start` 后等待机器人自动注册。
- **LLM 返回空内容**：若日志显示某模型返回空响应，会自动尝试候选列表；可在 `config.yaml` 中调整模型顺序或替换为稳定模型。
- **配置修改无效**：执行 `/nai插件重启` 或重启 AstraBot 载体。
- **自动质量词/负面词条不合适**：可在指令里手动覆盖，或在 `nl_settings` 中配置 `quality_words_override` / `negative_preset_override`。

## 参考资料

- QQ 使用说明：`HowToUse_QQ.md`
- Discord 使用说明：`HowToUse_Discord.md`
- LLM 提示词模板：`config.yaml` → `nl_settings.prompt_templates`
- API 适配与参数定义：参见 `main.py`、`parser.py`、`nl_processor.py`

欢迎针对更多场景自行扩展，或依据现有架构接入新的平台与模型。祝使用愉快！
