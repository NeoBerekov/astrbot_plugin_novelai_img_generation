# 部署与设置指南

`astrbot_plugin_novelai_img_generation` 是 AstraBot 的 NovelAI 官方 API 插件。

---

## 1. 环境与依赖

1. **克隆/解压 AstraBot 仓库** 并确保 Python ≥ 3.10。
2. **安装依赖**
   ```bash
   pip install -r AstrBot/data/plugins/astrbot_plugin_novelai_img_generation/requirements.txt
   ```
3. **准备运行环境**
   - 推荐执行 `AstrBot/start_astrbot.bat`（自动激活 `astrbot` 虚拟环境并运行 `uv run main.py`）。
   - 首次启动插件会自动生成 `config.yaml` 及白名单模板，请保留写权限。

---

## 2. 配置 `config.yaml`

文件路径：`AstrBot/data/plugins/astrbot_plugin_novelai_img_generation/config.yaml`

| 字段 | 说明 | 示例 |
| --- | --- | --- |
| `nai_token` | NovelAI 官方 Token | `"sk-..."` |
| `proxy` | HTTP/HTTPS 代理（可为空） | `"http://127.0.0.1:7890"` |
| `default_model` | 默认生图模型 | `"nai-diffusion-4-5-curated"` |
| `image_save_path` | **绝对路径**，按日期存图 | `"D:/NovelaiOutputs"` |
| `preset_uc` | 负面词条预设 | `"lowres, bad anatomy"` |
| `quality_words` | 自动补充的质量词 | `"best quality, masterpiece"` |
| `default_daily_limit` | 新用户每日额度 | `10` |
| `admin_qq_list` | QQ 管理员账号 | `[12345678]` |

### 自然语言模式（可选）

填充 `nl_settings` 可启用 `/nainl`：
```yaml
nl_settings:
  llm_provider: "openrouter"
  openrouter:
    api_key: "sk-..."
    models:
      - "openai/gpt-5-mini:online"
    timeout: 120
```
若留空则自动禁用。

---

## 3. 白名单与限额

| 平台 | 文件 | 作用 |
| --- | --- | --- |
| QQ | `data/aiocqhttp/whitelist.json` | 用户/群白名单、每日额度、昵称记录 |
| Discord | `data/discord/whitelist.json` | 用户白名单与额度 |

示例：
```json
{
  "users": {
    "12345678": {
      "daily_limit": 10,
      "remaining": 10,
      "last_reset": "2025-11-07",
      "nickname": "示例用户"
    }
  }
}
```

- 文件缺失时会自动生成。
- 可通过 `/nai白名单`、`/nai群白名单`、`/nai_whitelist_add` 等指令动态维护。

---

## 4. 启动与重载

1. **启动**
   - 运行 `AstrBot/start_astrbot.bat`，或在已激活环境中执行 `uv run main.py`。
2. **热重载**
   - 内部指令 `/nai插件重启` 会重新读取 `config.yaml` 与白名单，通常无需重启 AstraBot。

---

## 5. 常见部署问题

- **图片未写出**：确认 `image_save_path` 为可写的绝对路径。
- **QQ 无响应**：检查白名单、额度、Token 与代理；确保未触发限额。
- **Discord Slash 命令缺失**：重新邀请机器人并赋予 `applications.commands` 权限，稍待同步。
- **LLM 超时**：提高 `nl_settings.openrouter.timeout` 或更换更稳定的模型/代理。
- **设置未生效**：执行 `/nai插件重启`，或直接重启 `start_astrbot.bat`。

如需终端用户指令说明，请参考 `HowToUse_QQ.md` / `HowToUse_Discord.md`。祝部署顺利！

