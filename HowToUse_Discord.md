# Discord 平台使用指南

本指南面向在 Discord 中使用本插件的终端用户，介绍 Slash 命令、自然语言模式与常见管理方式。

---

## 1. 基本概念

1. **指令形式**：机器人会在服务器中自动注册 Slash 命令（如 `/nai`、`/nainl`、`/nai_whitelist_add`）。在聊天框中输入 `/` 后直接选择，无需手动敲命令头。
2. **白名单**：管理员需先把你的账号加入白名单；Discord 平台默认不启用群白名单，机器人会在部署的频道中直接响应。
3. **每日限额**：每个账号都有独立的每日额度，达到上限会提示“每日限额已达”，次日自动恢复。

---

## 2. `/nai` 文本生成

在 Slash 命令面板选择 `/nai`，主要字段如下：

| 选项 | 说明 | 默认行为 |
| --- | --- | --- |
| prompt | 正面提示词 | **必填**；斜杠面板会提示为 `prompt` |
| negative_prompt | 负面提示词 | 留空时自动使用 `config.yaml` → `preset_uc`，若配置为空则回退到 Heavy 预设 |
| resolution / steps / sampler / guidance 等 | 与 QQ 平台一致 | 未填写时使用默认值（竖图、步数 28、采样器 `k_euler_ancestral` 等） |
| add_quality_words | 是否追加质量词 | 默认为 `否`；若主提示词缺少 `best quality` 与 `masterpiece` 会自动补齐 |
| character	n / position	n | 角色提示词与位置 | 最多 5 位角色，位置为 A1~E5 网格 |
| model | 指定模型 | 默认使用 `default_model` |

> 只填写 `prompt` 也没问题，插件会提示已将全文作为正面词条。

---

## 3. `/nainl` 自然语言生成

`/nainl` 允许你直接输入自然语言描述：

1. 发送命令后，机器人会立即回复“自然语言交由 LLM 分析中，请稍后~”。
2. LLM 会判断描述是否详细，选择扩写或翻译模板。
3. 模板第一步会识别描述中的角色名称：若疑似有出处，会自动查询中文官方英文名→danbooru 标准 tag，并在最终提示词中使用标准名称。
4. 生成的正面提示词会根据配置自动补充质量词 / 负面词条。
5. 队列完成后，返回图片并在提示语中标注使用的 LLM 模型。

可选选项：

- `auto_add_quality_words`（布尔值）控制是否在 LLM 输出后追加质量词。
- 其他 `/nai` 中可选的参数也可透过选项面板传入，自然语言与结构化参数可以混合使用。

---

## 4. 帮助与辅助指令

- `/naihelp`：机器人返回完整的参数模板，包含所有字段和说明。
- `/naiplugin_reload`（对应 `/nai插件重启`）**暂未在 Slash 中提供**，若需要热加载配置，可在 QQ 平台执行或直接重启机器人进程。

---

## 5. 白名单管理（管理员）

| 指令 | 功能 |
| --- | --- |
| `/nai_whitelist_add user:<成员> nickname:<可选昵称>` | 添加或更新用户白名单；昵称留空会自动使用现有昵称/用户名 |
| `/nai_whitelist_remove user:<成员>` | 移除用户白名单 |
| `/nai_limit_set user:<成员> limit:<次数> nickname:<可选昵称>` | 若已注册该命令，可以直接在 Discord 端调整每日限额（若未注册，可在 QQ 端执行 `/nai限额 设置 ...`） |

系统会将白名单持久化到 `AstrBot/data/plugins/astrbot_plugin_novelai_img_generation/data/discord/whitelist.json`，包含账号 ID、昵称、每日限额、剩余额度、上次使用时间等信息。

---

## 6. 队列与输出

- 每个请求进入异步队列，系统在两次生成之间插入 3~5 秒随机延迟。
- 生成成功后会在同一频道回复图片，并包含模型、种子以及“LLM: xxx”提示。
- 图片文件保存在 `config.yaml` → `image_save_path` 下的日期目录中。

---

## 7. 常见问题

1. **Slash 命令不生效**：确认机器人具备 `applications.commands` 权限；若首次添加后仍看不到命令，等待几分钟或重新邀请机器人即可。
2. **提示缺少 prompt**：`/nai` 必须填写 `prompt` 字段，`/nainl` 需要填写 `text` 字段。
3. **LLM 返回空内容**：日志会提醒“模型返回空内容，尝试下一个模型”，系统会自动切换到候选列表的下一项。可在 `config.yaml` 调整模型顺序或去掉无效模型。
4. **达到每日限额**：等待次日重置，或联系管理员通过白名单文件/命令调整。
5. **希望关闭自动质量词**：`/nai` 可设置 `添加质量词:<否>`，`/nainl` 可填写 `是否自动添加质量词:<否>`。

---

## 8. 数据位置速查

- 配置文件：`AstrBot/data/plugins/astrbot_plugin_novelai_img_generation/config.yaml`
- Discord 白名单：`.../data/discord/whitelist.json`
- 生成图片：`config.yaml` 指定的 `image_save_path/日期/`

如需进一步的参数说明或跨平台管理示例，请参考仓库根目录的 `README.md`。祝你在 Discord 上玩得愉快！
