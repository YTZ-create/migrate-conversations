<div align="center">

# migrate-conversations

**把任意 AI 工具的历史对话，批量搬进你正在用的 AI 工具，变成一个个能接着聊的独立会话。**

同一套思路（自动扫描 → 按项目匹配 → 导出 → 变成可续聊的独立会话），两种落地。按你的目标工具二选一。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![No runtime deps](https://img.shields.io/badge/deps-none-success)](./migrate-conversations-to-trae/SKILL.md)
[![up to 17 AI tools](https://img.shields.io/badge/sources-up%20to%2017%20AI%20tools-green)](./migrate-conversations-to-trae/references/sources.md)

</div>

这是一族**平级**的技能，每个只负责一个目标工具：

| | 🟦 迁进 Qoder | 🟩 迁进 Trae |
|---|---|---|
| 目录 | [migrate-conversations-to-qoder/](./migrate-conversations-to-qoder/) | [migrate-conversations-to-trae/](./migrate-conversations-to-trae/) |
| 运行环境 | **仅 Qoder** | **Trae**（含 Trae SOLO CN） |
| 自动化程度 | 全自动建会话（近乎一键） | 扫描/导出全自动；**建会话需手动粘贴** |
| 依赖 | Qoder 内置 `create_chat_session` 等 4 个工具 | Python 3（仅标准库） |
| 建会话方式 | 程序化创建（不可逆，建错只能在 UI 删） | 生成种子提示词，你在 UI 新建会话粘贴 |
| 支持来源 | 13 类 | **17 类**（多出 Qoder 本身 / Marvis / LM Studio / OpenClaw / ZCode / Copilot Chat；两者各有对方没有的来源） |

## 怎么选

- 目标就是 **Qoder** → 用 [migrate-conversations-to-qoder](./migrate-conversations-to-qoder/)，体验最顺，能自动建会话。
- 目标就是 **Trae** → 用 [migrate-conversations-to-trae](./migrate-conversations-to-trae/)。Trae 没有程序化建会话的接口，所以走「导出 + 粘贴种子提示词」的半自动路线。

## 共同工作原理

```mermaid
flowchart LR
    A["给一个项目标识<br/>URL / 仓库名 / 文件夹名"] --> B["自动扫描本地 AI 工具"]
    B --> C["按项目路径 / 内容关键词<br/>匹配相关会话"]
    C --> D["你选择要迁移哪些"]
    D --> E["导出为 Markdown"]
    E --> F["变成一个个<br/>能接着聊的独立会话"]
```

## 支持的 AI 工具（来源）

两个版本各自支持的来源**并不完全相同**：**Qoder 版 13 类**、**Trae 版 17 类**（各有对方没有的来源）。

**逐工具的版本对照矩阵**、不支持项与细节 → **[SOURCES.md](./SOURCES.md)**

## 安装

克隆本仓库，把要用的那个 skill 目录放进对应环境的技能目录。

### 迁进 Qoder

```bash
git clone https://github.com/YTZ-create/migrate-conversations.git /tmp/mc
# 用户级
cp -r /tmp/mc/migrate-conversations-to-qoder ~/.qoder-cn/skills/
# 项目级：目标换成 <你的项目>/.qoder/skills/
```

```powershell
# Windows PowerShell
git clone https://github.com/YTZ-create/migrate-conversations.git "$env:TEMP\mc"
Copy-Item -Recurse -Force "$env:TEMP\mc\migrate-conversations-to-qoder" "$env:USERPROFILE\.qoder-cn\skills\"
```

### 迁进 Trae

```bash
git clone https://github.com/YTZ-create/migrate-conversations.git /tmp/mc
cp -r /tmp/mc/migrate-conversations-to-trae <你的项目>/.trae/skills/
```

```powershell
# Windows PowerShell
git clone https://github.com/YTZ-create/migrate-conversations.git "$env:TEMP\mc"
Copy-Item -Recurse -Force "$env:TEMP\mc\migrate-conversations-to-trae" "<你的项目>\.trae\skills\"
```

装好后：Qoder 执行 `/skills reload`（或重启会话）；Trae 重开一个对话即可识别。

## 使用（一句话）

- **Qoder**：`/migrate-conversations-to-qoder <GitHub URL 或项目名>` —— 详见[该 skill 的 README](./migrate-conversations-to-qoder/README.md)。
- **Trae**：在对话里说「把 &lt;项目&gt; 的 &lt;来源工具&gt; 里的对话导到 Trae」—— 详见[该 skill 的 README](./migrate-conversations-to-trae/README.md)。

## 安全与隐私

- 全程**只读**来源数据，绝不修改任何原始文件。
- SQLite 一律以只读方式打开（先复制到临时目录再 `mode=ro`）。
- 导出的 Markdown 与种子提示词都是临时产物，完成后可自行删除。
- 不迁移「记忆 / memory」，只迁对话正文。

## License

[MIT](./LICENSE) © 2026 YTZ-create