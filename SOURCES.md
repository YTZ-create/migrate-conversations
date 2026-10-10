<div align="center">

# 支持的 AI 工具（来源）

两个 skill 共用同一套来源探测能力。本文件是来源清单的唯一权威版本。

</div>

| 类别 | 工具 |
|---|---|
| AI 编辑器 | Qoder、Cursor、Windsurf |
| 本地 CLI | Claude Code、Codex CLI、Gemini CLI、Kimi Code、Copilot CLI |
| 桌面应用 | 豆包 Doubao、Chatbox、MiMo 小米、Marvis 腾讯、LM Studio |
| 智能体 / 轨迹 | OpenClaw、ZCode |
| 编辑器插件 | VS Code Copilot Chat |
| 官方导出 | ChatGPT、Claude Web（需先在官方设置导出 `conversations.json` 放到 Downloads） |

> - **Qoder 版**覆盖其中 **13 类**。
> - **Trae 版**覆盖全部 **17 类**。

**不支持**：Trae 会话本身（SQLCipher 加密，读不出）、Perplexity / 文心一言 / 通义千问（无本地结构化数据）。

## 各来源的读取细节

- **Trae 版**：逐来源的路径、字段与可靠性分级（A / B / C）见 [migrate-conversations-to-trae/references/sources.md](./migrate-conversations-to-trae/references/sources.md)。
- **Qoder 版**：来源与匹配规则见 [migrate-conversations-to-qoder/SKILL.md](./migrate-conversations-to-qoder/SKILL.md)。