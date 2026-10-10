<div align="center">

# 支持的 AI 工具（来源）

本文件是来源清单的唯一权威版本：逐工具标注 **Qoder 版 / Trae 版**是否支持。

</div>

| 类别 | 工具 | 数据位置 / 格式 | Qoder 版 | Trae 版 |
|---|---|---|:---:|:---:|
| AI 编辑器 | **Qoder** | `%APPDATA%/com.qodercn.app.stable/main.sqlite` · SQLite | — | ✅ |
| AI 编辑器 | Cursor | `%APPDATA%/Cursor/User/workspaceStorage/<hash>/state.vscdb` · SQLite | ✅ | ✅ |
| AI 编辑器 | Windsurf | `%APPDATA%/Windsurf/User/workspaceStorage/<hash>/state.vscdb` · SQLite | ✅ | ✅ |
| 本地 CLI | Claude Code | `~/.claude/projects/<项目>/*.jsonl` · JSONL | ✅ | ✅ |
| 本地 CLI | Codex CLI | `~/.codex/sessions/YYYY/MM/DD/*.jsonl` · JSONL | ✅ | ✅ |
| 本地 CLI | Gemini CLI | `~/.gemini/tmp/<hash>/chats/session-*.json` · JSON | ✅ | ✅ |
| 本地 CLI | Kimi Code | `~/.kimi-code/**/*.json(l)` · JSONL / JSON | ✅ | ✅ |
| 本地 CLI | GitHub Copilot CLI | `~/.copilot/session-state/**` · JSONL / SQLite | ✅ | ✅ |
| 桌面应用 | 豆包 Doubao | `%LOCALAPPDATA%/Doubao/**/trajectory.jsonl` · JSONL | ✅ | ✅ |
| 桌面应用 | Chatbox | `%APPDATA%/xyz.chatboxapp.app/config.json` · JSON | ✅ | ✅ |
| 桌面应用 | MiMo 小米 | `~/.local/share/mimocode/mimocode.db` · SQLite | ✅ | ✅ |
| 桌面应用 | Claude Desktop | `%APPDATA%/Claude/sessions/` · JSONL | ✅ | — |
| 桌面应用 | Marvis 腾讯 | `~/.marvis/database/data.db` · SQLite | — | ✅ |
| 桌面应用 | LM Studio | `~/.lmstudio/conversations/*.conversation.json` · JSON | — | ✅ |
| 智能体 / 轨迹 | OpenClaw | `~/.openclaw/agents/main/sessions/<uuid>.jsonl` · JSONL | — | ✅ |
| 智能体 / 轨迹 | ZCode | `~/.zcode/cli/agents/**/transcript.jsonl` · JSONL | — | ✅ |
| 编辑器插件 | VS Code Copilot Chat | `<编辑器>/User/globalStorage/github.copilot-chat/session-store.db` · SQLite | — | ✅ |
| 官方导出 | ChatGPT | `~/Downloads/conversations.json` · JSON | ✅ | ✅ |
| 官方导出 | Claude Web | `~/Downloads/conversations.json` · JSON | ✅ | ✅ |

> ✅ = 该版本支持；— = 不支持。Windows 上 `~` 即 `C:\Users\<用户名>`；`%APPDATA%` = `...\AppData\Roaming`，`%LOCALAPPDATA%` = `...\AppData\Local`。
>
> - **Qoder 版**：支持 **13 类**。
> - **Trae 版**：支持 **17 类**（其中 ChatGPT 与 Claude Web 的官方导出合并计为 1 类来源）。

**差异速览**

- **Trae 版比 Qoder 版多支持**：Qoder 本身、Marvis 腾讯、LM Studio、OpenClaw、ZCode、VS Code Copilot Chat。
- **Qoder 版比 Trae 版多支持**：Claude Desktop。

**两个版本都不支持**：Trae 会话本身（SQLCipher 加密，读不出）、Perplexity / 文心一言 / 通义千问（无本地结构化数据）。

## 各来源的读取细节

- **Trae 版**：逐来源的字段与可靠性分级（A / B / C）、解析细节见 [migrate-conversations-to-trae/references/sources.md](./migrate-conversations-to-trae/references/sources.md)。
- **Qoder 版**：来源与匹配规则见 [migrate-conversations-to-qoder/SKILL.md](./migrate-conversations-to-qoder/SKILL.md)。