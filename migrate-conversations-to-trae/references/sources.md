# 各来源的路径、格式与可靠性

本文件供排查用。`可靠性` 分三档：
**A = 格式稳定、匹配精确**（有项目路径字段）；**B = 能读，靠内容关键词匹配**；**C = 尽力而为**（格式随版本变动）。

| 来源 | 默认路径 | 格式 | 项目匹配 | 可靠性 |
| --- | --- | --- | --- | --- |
| Qoder（国内版） | `%APPDATA%/com.qodercn.app.stable/main.sqlite` | SQLite（明文） | `chat_sessions.cwd` = 项目路径 | A |
| Qoder（国际版） | `%APPDATA%/Qoder/main.sqlite`、`%LOCALAPPDATA%/Qoder CN/main.sqlite` | SQLite（明文） | 同上 | A |
| Claude Code | `~/.claude/projects/<转义项目路径>/*.jsonl` | JSONL | 目录名 = 项目路径转义（`:` `\` `/` → `-`） | A |
| Codex CLI | `~/.codex/sessions/YYYY/MM/DD/*.jsonl`；旧版 `~/.codex/history.jsonl` | JSONL | 首行 `session_meta.payload.cwd` | A |
| Gemini CLI | `~/.gemini/tmp/<hash>/chats/session-*.json`；兼容 `logs.json` | JSON | `chats` 同级 `.project_root`，否则内容关键词 | B |
| Kimi Code | `~/.kimi-code/**/*.json(l)` | JSONL/JSON | 内容关键词 | C |
| Copilot CLI | `~/.copilot/session-state/**`（`~/.copilot`） | JSONL / SQLite | 内容关键词 | C |
| Cursor | `%APPDATA%/Cursor/User/workspaceStorage/<hash>/state.vscdb` | SQLite | `workspace.json.folder` = 项目路径 | A |
| Windsurf | `%APPDATA%/Windsurf/User/workspaceStorage/<hash>/state.vscdb` | SQLite | 同 Cursor | B |
| 豆包 Doubao | `%LOCALAPPDATA%/Doubao/**/trajectory.jsonl` | JSONL | 内容关键词 | C |
| Chatbox | `%APPDATA%/xyz.chatboxapp.app/config.json` | JSON | 无路径，标题/内容关键词 | B |
| MiMo 小米 | `~/.local/share/mimocode/mimocode.db` | SQLite（明文） | `session.directory` = 项目路径 | A |
| MiMo 桌面版 | 同上（桌面版共用 `mimocode.db` 引擎） | SQLite（明文） | 同上 | A |
| Marvis 腾讯 | `~/.marvis/database/data.db` | SQLite（明文） | 无路径，标题/内容关键词 | B |
| LM Studio | `~/.lmstudio/conversations/*.conversation.json` | JSON | 无路径，标题/内容关键词 | B |
| OpenClaw | `~/.openclaw/agents/main/sessions/<uuid>.jsonl` | JSONL | `session.cwd` = 项目路径 | A |
| ZCode | `~/.zcode/cli/agents/<sess>/agent_<id>/transcript.jsonl` | JSONL | `~/.zcode/v2/tasks-index.sqlite` 的 `workspace_path` | A |
| Copilot Chat | `%APPDATA%/<编辑器>/User/globalStorage/github.copilot-chat/session-store.db` | SQLite（WAL） | `sessions.cwd` / `repository` | B |
| ChatGPT | `~/Downloads/conversations.json` | JSON | 内容关键词 | B |
| Claude Web | `~/Downloads/conversations.json` | JSON | 内容关键词 | B |

> Windows 上 `~` 即 `C:\Users\<用户名>`；`%APPDATA%` = `C:\Users\<用户名>\AppData\Roaming`，`%LOCALAPPDATA%` = `...\AppData\Local`。

## 关键解析细节

- **Qoder**
  - 表 `chat_sessions`：`session_id` / `title` / `cwd` / `created_at` / `updated_at`（毫秒时间戳）/ `archived` / `deleted_at`。
    过滤掉 `archived = 1` 与 `deleted_at` 非空的记录。
  - 表 `chat_session_messages`：`session_id` / `sequence` / `payload_json`，按 `sequence` 排序。
    `payload_json` 里有 `role`（`user` / `assistant` / `system`）和 `text`；`subtype = "hook_activity"` 及空 `text` 的记录跳过。
  - 不同 Qoder 版本的表结构可能增删字段；脚本对缺字段做了容错（读不到就跳过该库）。
  - 注意：Qoder 官方文档称会话标题存在加密 `state.json`；实测国内版 `main.sqlite` 是**明文**，可直接读。
- **Claude Code**
  - 一行一条记录，`type` ∈ `user` / `assistant` / `summary` / `system`。
  - 项目目录名是 cwd 的转义：`C:\a\b` → `c--a-b`。
  - 跳过 `isSidechain: true`（子代理）；跳过整条都是 `tool_result` 的用户消息。
  - 正文里的 `<ide_opened_file>` / `<ide_selection>` / `<system-reminder>` 会被清掉再入档。
- **Codex CLI**
  - `event_msg`（`user_message` / `agent_message`）优先；没有则退回 `response_item` 的 `message`。
  - 跳过 `agent_reasoning`。
- **Cursor**
  - 表 `cursorDiskKV(key, value)`；`composerData:<id>` 存会话元信息（含 `name`、`fullConversationHeadersOnly` 排序），`bubbleId:<composerId>:<bubbleId>` 存单条消息（`type`: 1=用户，2=助手）。
  - 有 `fullConversationHeadersOnly` 时按它排序；否则按 `createdAt`。
- **Windsurf**
  - 表 `ItemTable(key, value)`，key 含 `chatdata` / `aichat` / `cascade` 的值里藏对话，用通用递归提取。
- **ChatGPT 导出**：`conversations[].mapping` 是树，需从根沿 `children` 线性化。
- **Claude Web 导出**：`conversations[].chat_messages[].sender` ∈ `human` / `assistant`。
  - 两种导出都叫 `conversations.json`，脚本按结构自动区分（有 `mapping` = ChatGPT，有 `chat_messages` = Claude）。
- **MiMo 小米 / MiMo 桌面版**（`mimocode.db`，明文 SQLite）
  - 表 `session`：`id` / `title` / `directory`（项目路径）/ `time_created` / `time_updated`。
  - 表 `message`：`id` / `session_id` / `data`（JSON，含 `role`），按 `time_created` 排序。
  - 表 `part`：`message_id` / `data`（JSON，`type = "text"` 时取 `text`），按 `time_created` 排序；同一 `message_id` 的多个 part 拼接成正文。
  - 桌面版 `%APPDATA%/Xiaomi MiMo/db/*.db` 只有 artifacts（文件产物），对话正文仍在 `mimocode.db`。
- **Marvis 腾讯**（`data.db`，明文 SQLite）
  - 表 `conversations`：`conversation_id` / `title` / `created_at` / `updated_at`。
  - 表 `messages`：`conversation_id` / `role` / `content` / `message_seq`，按 `message_seq` 排序。
  - 另有 `agui_events`（59670 行的事件流）体积大且是增量事件，不采用，直接读 `messages` 更干净。
- **LM Studio**（`*.conversation.json`）
  - 顶层 `name` / `createdAt` / `messages`；每条 `messages[]` 是 `{versions: [...], currentlySelected: N}`。
  - 取 `versions[currentlySelected]`：`singleStep` 直接读 `content`，`multiStep` 读 `steps[].content`。
- **OpenClaw**（`agents/main/sessions/<uuid>.jsonl`）
  - 每行一个事件；`{"type":"message","message":{"role","content":[...]}}` 即正文。
  - `{"type":"session",...,"cwd":...}` 提供项目路径；`compaction` / `model_change` / `custom` 等事件忽略。
  - `*.trajectory.jsonl` 是运行轨迹（`context.compiled` / `prompt.submitted` / `model.completed`），正文不完整，跳过。
- **ZCode**（`transcript.jsonl`）
  - 事件类型：`turn_started` / `model_request` / `model_streaming` / `model_complete` / `tool_call_*`。
  - `model_request.payload.messages` 带完整累积上下文；取**最后一条** `model_request` 即完整对话（失败或半途会话可能没有 `model_complete`）。
  - 目录名 `sess_subagent_*` 为子代理轨迹，跳过以免重复；`tasks-index.sqlite` 的 `tasks(task_id, title, workspace_path)` 提供标题与项目路径。
- **Copilot Chat**（`session-store.db`）
  - 表 `sessions`（`id` / `cwd` / `repository` / `summary` / 时间）、表 `turns`（`session_id` / `turn_index` / `user_message` / `assistant_response`）。
  - 新版本数据常驻 `-wal`：脚本把 `.db` `-wal` `-shm` 一起复制到临时目录再只读打开，否则会读到 0 行。

## 明确不支持的来源

| 来源 | 原因 |
| --- | --- |
| **Trae** | 会话存在 SQLCipher 加密的 `database.db`（文件头非 `SQLite format 3`），既读不出也写不进 |
| Perplexity / 文心一言 / 通义千问 | 纯 Web 服务，本地没有结构化对话数据 |
| 豆包「普通聊天」（非 agent 模式） | 可能存在 LevelDB 中，本脚本优先读 `trajectory.jsonl` |
| sessionharbor-desktop / local-agent-4 | 仅 Chromium 缓存与空 LevelDB（`Local Storage` 只有几十字节），无对话正文 |
| WorkBuddy / CodeBuddy | `~/.workbuddy/sessions/*.json` 只是进程心跳元数据，非对话 |
| `.qwen-agent` / `.ai_completion` / `.copilot`（CLI 日志） | 只有偏好配置与运行日志，没有对话正文 |
| Kimi 桌面版 | `%APPDATA%/kimi-desktop/kimi-agent/*.json` 只有元数据，正文在 IndexedDB，暂不解析 |

## 为什么不能像 Qoder 版那样自动建会话

Qoder 版依赖 Qoder 内置的 `create_chat_session` / `list_chat_sessions` / `read_chat_session` / `wait_chat_sessions`。
Trae 没有这组工具，CLI（`bin/trae-solo-cn.cmd` → VSCode `cli.js`）也只支持打开文件 / 装扩展，不带建会话命令。
因此"新建会话"这一步只能由用户在界面上完成——这是环境限制，不是本技能可以绕过的。