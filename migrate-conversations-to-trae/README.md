<div align="center">

# migrate-conversations-to-trae

**把你在别的 AI 工具里的历史对话，搬进 Trae，接着往下聊。**

自动扫描本地 **17 类 AI 工具**，找到与当前项目相关的会话，导出成带完整上下文的 Markdown，并生成可直接粘贴的「种子提示词」。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](../LICENSE)
[![Type: Trae Skill](https://img.shields.io/badge/type-Trae%20Skill-blueviolet)](./SKILL.md)
[![Python 3 · stdlib only](https://img.shields.io/badge/deps-Python%203%20stdlib-blue)](./scripts/trae_migrate.py)
[![17 AI tools](https://img.shields.io/badge/sources-17%20AI%20tools-green)](./references/sources.md)

</div>

> 🔗 本仓库是「迁移对话到任意 AI 工具」家族仓库，这是 **Trae 版**。想看 **Qoder 版**或家族总览，见 [仓库根 README](../README.md)。

## 它解决什么问题

你过去在 Qoder、Claude Code、Cursor、豆包、Marvis、MiMo……这些工具里聊过的项目对话，**不用再翻旧记录、不用重新解释背景**，可以直接在 Trae 里"接着聊"。

## ⚠️ 先说清楚的硬限制

Trae **没有** Qoder 那样的 `create_chat_session` 等内置工具，助手**无法程序化新建 Trae 会话**；Trae 自身的会话库也是 SQLCipher 加密的（既读不出也写不进）。

所以本技能定位是 **「全自动扫描 + 导出，手动建会话」**：

- **全自动**：扫描来源 → 按项目筛选 → 导出 Markdown → 生成种子提示词与对照表。
- **需手动**：你在 Trae 里**逐个新建会话并粘贴种子提示词**，每个几秒钟。

> 不像 Qoder 版那样"一键建好会话"——这是环境限制，不是本技能能绕过的。

## 工作流（三步）

```
① 扫描  →  ② 导出  →  ③ 你在 Trae 里粘贴（这一步由你手动完成）
```

```mermaid
flowchart LR
    A["给一个项目标识<br/>URL / 仓库名 / 文件夹名"] --> B["① 扫描<br/>列出相关会话"]
    B --> C["你选择要导出的序号"]
    C --> D["② 导出<br/>Markdown + 种子提示词"]
    D --> E["③ 新建 Trae 会话<br/>粘贴种子提示词"]
    E --> F["带完整上下文<br/>接着聊"]
```

### 第 1 步 · 扫描

在 Trae 对话里直接说，例如：

```
帮我把以前的对话导入到 Trae，只看 OpenClaw 这个项目的
```

或显式点名技能：

```
/migrate-conversations-to-trae https://github.com/YTZ-create/OpenClaw
```

技能会探测本地 17 类来源并汇报：

```
本地 AI 工具扫描结果（共探测 17 类来源）：

✅ Qoder        — 共 32 个会话，匹配 27 个
✅ Claude Code  — 共 17 个会话，匹配 12 个
✅ MiMo 小米    — 共 13 个会话，匹配 8 个
❌ Cursor       — 未安装 / 无可读数据

共找到 27 个相关会话，要导出哪几个？（序号 / 1-4 / all）
```

### 第 2 步 · 导出

回复要导出的序号（如 `1,2,5` 或 `all`），技能生成：

- `_migrate_export/<序号>-<标题>.md` —— 每个会话一份历史记录
- `_migrate_export/_index.md` —— 对照表 + 每个会话的**种子提示词**
- `_manifest.json` —— 已导出清单（用于幂等）

### 第 3 步 · 在 Trae 里粘贴

1. 打开 `_index.md`，找到某个会话的**种子提示词**。
2. 在 Trae 里**新建会话** → 整段粘贴 → 发送。
3. Trae 会先 `Read` 那份历史 md，读完即带完整上下文，你接着说。
4. 改名建议**从列表底部往上改**（改名会顶到最前）。
5. 全部确认后，可删除 `_migrate_export/`（纯临时产物）。

## 支持的 AI 工具（17 类）

覆盖 **17 类**本地 AI 工具。完整清单与不支持项见 **[../SOURCES.md](../SOURCES.md)**；
本 skill 逐来源的路径、字段与可靠性分级见 [references/sources.md](./references/sources.md)。

## 安装

Trae 技能放在项目的 `.trae/skills/` 下（项目级）：

```bash
git clone https://github.com/YTZ-create/migrate-conversations-to-qoder.git /tmp/mc
cp -r /tmp/mc/migrate-conversations-to-trae <你的项目>/.trae/skills/
```

```powershell
# Windows PowerShell
git clone https://github.com/YTZ-create/migrate-conversations-to-qoder.git "$env:TEMP\mc"
Copy-Item -Recurse -Force "$env:TEMP\mc\migrate-conversations-to-trae" "<你的项目>\.trae\skills\"
```

装好后重开一个对话即可识别。脚本只用 Python 标准库，无需安装依赖。

## 手动跑脚本（可选）

技能内部调用如下命令；你也可以自己跑：

```bash
python "scripts/trae_migrate.py" scan  --project "<项目标识>" --out-dir ".trae-import"
python "scripts/trae_migrate.py" export --out-dir ".trae-import" --pick "1,2,5"

# 常用参数
--all                     # 不筛选，列出全部会话
--source "Cursor,Claude"  # 只看指定来源
```

Windows 上若无系统 Python，可用 Trae 内置解释器：
`%APPDATA%\TRAE SOLO CN\ModularData\ai-agent\vm\tools\python\python.exe`。

## 触发方式

默认靠语义自动触发，无需知道技能名字。带有下列意思之一即可：

> 「把对话**迁移 / 导入到 Trae**」「历史会话**搬进 Trae**」「把 Qoder / Cursor / 别的工具的对话**导进来**」「**接着之前的对话**继续聊」

想百分之百确定时，可显式点名：`用 migrate-conversations-to-trae 这个 skill …` 或 `/migrate-conversations-to-trae`。

## 常见问题

- **某个来源是 0 个会话**：关键词太窄、该工具还没用过，或数据在加密库里。换关键词或加 `--all` 再试。
- **ChatGPT / Claude Web 读不到**：先到官方设置导出数据，把 `conversations.json` 放到 `Downloads`，再重新扫描。
- **豆包 / Kimi / Copilot 结果不完整**：这些来源没有项目路径字段，只能靠内容关键词匹配，可能有漏网之鱼。
- **Cursor / Windsurf 读不到**：对话存在 `state.vscdb`，不同版本字段名会变；若为 0 属已知"尽力而为"。
- **能在 Trae 里自动建好吗**：不能，需手动新建会话 + 粘贴种子提示词（见上方硬限制）。
- **会不会动我原来的记录**：不会，全程只读；导出的是临时副本。

## 安全与隐私

- 全程**只读**来源数据，绝不修改任何原始文件。
- SQLite 一律以只读方式打开（先复制到临时目录再 `mode=ro`；Copilot Chat 会连同 `-wal`/`-shm` 一起复制）。
- 不迁移「记忆 / memory」，只迁对话正文。

## License

[MIT](../LICENSE) © 2026 YTZ-create