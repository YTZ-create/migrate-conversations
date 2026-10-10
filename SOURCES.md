<div align="center">

# 支持的 AI 工具（来源）

本文件是来源清单的唯一权威版本：逐工具标注 **Qoder 版 / Trae 版**是否支持。

</div>

| 类别 | 工具 | Qoder 版 | Trae 版 |
|---|---|:---:|:---:|
| AI 编辑器 | **Qoder** | — | ✅ |
| AI 编辑器 | Cursor | ✅ | ✅ |
| AI 编辑器 | Windsurf | ✅ | ✅ |
| 本地 CLI | Claude Code | ✅ | ✅ |
| 本地 CLI | Codex CLI | ✅ | ✅ |
| 本地 CLI | Gemini CLI | ✅ | ✅ |
| 本地 CLI | Kimi Code | ✅ | ✅ |
| 本地 CLI | GitHub Copilot CLI | ✅ | ✅ |
| 桌面应用 | 豆包 Doubao | ✅ | ✅ |
| 桌面应用 | Chatbox | ✅ | ✅ |
| 桌面应用 | MiMo 小米 | ✅ | ✅ |
| 桌面应用 | Claude Desktop | ✅ | — |
| 桌面应用 | Marvis 腾讯 | — | ✅ |
| 桌面应用 | LM Studio | — | ✅ |
| 智能体 / 轨迹 | OpenClaw | — | ✅ |
| 智能体 / 轨迹 | ZCode | — | ✅ |
| 编辑器插件 | VS Code Copilot Chat | — | ✅ |
| 官方导出 | ChatGPT | ✅ | ✅ |
| 官方导出 | Claude Web | ✅ | ✅ |

> ✅ = 该版本支持；— = 不支持。
>
> - **Qoder 版**：支持 **13 类**。
> - **Trae 版**：支持 **17 类**（其中 ChatGPT 与 Claude Web 的官方导出合并计为 1 类来源）。

**差异速览**

- **Trae 版比 Qoder 版多支持**：Qoder 本身、Marvis 腾讯、LM Studio、OpenClaw、ZCode、VS Code Copilot Chat。
- **Qoder 版比 Trae 版多支持**：Claude Desktop。

**两个版本都不支持**：Trae 会话本身（SQLCipher 加密，读不出）、Perplexity / 文心一言 / 通义千问（无本地结构化数据）。

## 各来源的读取细节

- **Trae 版**：逐来源的路径、字段与可靠性分级（A / B / C）见 [migrate-conversations-to-trae/references/sources.md](./migrate-conversations-to-trae/references/sources.md)。
- **Qoder 版**：来源与匹配规则见 [migrate-conversations-to-qoder/SKILL.md](./migrate-conversations-to-qoder/SKILL.md)。