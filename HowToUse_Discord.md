# Discord 平台使用指南

本指南面向在 Discord 中使用 NovelAI 图片生成插件的用户，说明 Slash 命令写法、白名单管理以及常见注意事项。

---

## 1. 基本说明

1. **Slash 命令**：机器人会注册 `/nai`、`/nai_whitelist_add`、`/nai_whitelist_remove` 等命令，在输入框内直接选择即可，无需手动输入 `/`。
2. **白名单**：
   - 管理员添加你的账号后，你才能使用 `/nai`。
   - Discord 平台默认不启用群白名单，部署在哪个频道就在哪些频道响应。
3. **每日限额**：机器人会统计每日使用次数，达到上限后需等待次日重置。

---

## 2. `/nai` 生图指令

在 Slash 命令列表中选择 `/nai`，然后填写参数：

- `prompt`：主提示词（对应“正面词条”）。
- `negative_prompt`：负面提示词，不填时会自动使用配置中的 `preset_uc`。
- 其他选项如 `resolution`、`steps`、`sampler` 等也可在命令面板里直接选择。
- 如果只填写 `prompt`，其余参数默认值与 QQ 平台一致。

生成后机器人会返回图片，并在消息中提及你。若你没有填写“负面词条”，机器人会在提示语中说明使用了预设负面词条。

---

## 3. 白名单管理命令

仅管理员可用：

- `/nai_whitelist_add user:<用户> nickname:<昵称 (可选)>`
  - 通过用户选项选择目标成员即可，昵称欄可留空。
- `/nai_whitelist_remove user:<用户>`
  - 同样从用户列表选择要移除的成员。

机器人会自动识别 Slash 命令中的用户 ID，并补全昵称后写入白名单。

---

## 4. 指令参数说明

| 选项名称 | 说明 | 默认值 |
| --- | --- | --- |
| prompt | 正面提示词 | 必填，无默认 |
| negative_prompt | 负面提示词 | 使用 `config.yaml` 中 `preset_uc`，为空时退回 Heavy 预设 |
| resolution | 分辨率 | `竖图` |
| steps | 步数 (≤28) | 28 |
| guidance | 指导系数 | 5 |
| sampler | 采样器 | `k_euler_ancestral` |
| characters / positions | 若启用角色分区，可指定角色词条和位置 | 不启用 |
| model | 模型 | `config.yaml` 中的 `default_model` |

> 如果提示词里缺少 `best quality` 或 `masterpiece`，插件会自动追加 `quality_words`。

---

## 5. 归档与白名单位置

- 白名单数据存放在 `AstrBot/data/config/discord/whitelist.json`。
- 每位成员在白名单中会记录 ID、昵称、每日限额、剩余次数等信息。

---

## 6. 常见问题

1. **提示“缺少 /nai 开头”**：Slash 命令已经修复这一问题，若仍出现，请确认你填写了 `prompt`。
2. **无法添加白名单**：确认你有管理员权限，并使用 `/nai_whitelist_add` 进行添加；命令会自动填入昵称。
3. **每日限额达到**：等待次日重置或联系管理员通过 QQ 平台命令调整限额。
4. **只填写 prompt**：插件会提示“已将全文作为提示词”，这是正常的自动处理。

---

## 7. 建议

- 打开 Slash 命令的自动补全，可以避免格式错误。
- 提示词可以从简单到复杂逐步尝试，熟悉风格后再添加更多细节。
- 若需要和 QQ 平台同步管理，管理员可以到 `AstrBot/data/config/discord/whitelist.json` 中查看或编辑记录。

希望这份指南能帮助你快速上手 Discord 平台的生图功能！
