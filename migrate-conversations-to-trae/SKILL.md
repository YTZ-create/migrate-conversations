---
name: "migrate-conversations-to-trae"
description: "扫描本地 AI 工具(Qoder / Claude Code / Codex / Cursor / Windsurf / Gemini / Kimi / Copilot / Copilot Chat / MiMo / Marvis / LM Studio / OpenClaw / ZCode / 豆包 / Chatbox / ChatGPT·Claude 导出)的历史对话，按项目筛选并导出为 Markdown，生成可直接粘贴的种子提示词，让这些对话能在 Trae 里接着聊。当用户说「把对话迁移/导入到 Trae」「历史会话搬进 Trae」「把 Qoder/其它工具的对话导进来」「继续之前的对话」时使用。"
---

# 把历史对话迁移到 Trae

把你在其它 AI 工具里积累的历史对话，导出成一份份带完整上下文的 Markdown，并生成「种子提示词」，
让你能在 Trae 里把它们变成一个个能接着聊的独立会话。

## 触发方式与标准问法

**默认靠语义自动触发**，用户不需要知道本 skill 的名字，也无需提前说明要用它。只要话里带有下列意思之一，就应进入本流程：

> 「把对话**迁移 / 导入到 Trae**」「历史会话**搬进 Trae**」「把 Qoder / Cursor / 别的工具的对话**导进来**」「**接着之前的对话**继续聊」

**标准问法（可直接照抄）：**

- 最省事：`帮我把以前的对话导入到 Trae`
- 加项目（匹配更准）：`把我的对话导进 Trae，只看 <项目名 / 仓库链接 / 本地路径> 的`
- 指定来源：`把我在 <Qoder / Cursor / Claude Code …> 里的对话导到 Trae`
- 扫描后选择：`都导` / `只要 1、2、5` / `1 到 4 号`

**想百分之百确定时，可显式点名**：`用 migrate-conversations-to-trae 这个 skill …` 或 `/migrate-conversations-to-trae`。
用户话较模糊（如只说"整理一下以前的记录"）时，建议其点名，避免走偏。

## ⚠️ 必须先说清楚的硬限制（不要对用户隐瞒）

Trae **没有** Qoder 那样的 `create_chat_session` / `list_chat_sessions` 内置工具，助手**无法程序化新建 Trae 会话**；
Trae 自身的会话库也是 SQLCipher 加密的（既读不出也写不进）。

所以本技能的定位是 **「全自动扫描 + 导出，手动建会话」**：

- **全自动**：扫描本地来源 → 按项目筛选 → 导出 Markdown → 生成种子提示词与对照表。
- **需手动**：用户在 Trae 里**逐个点「新建会话」并粘贴种子提示词**。每个会话花几秒。

**不要**向用户承诺"一键批量在 Trae 里创建好会话"，那是做不到的。要如实说明。

## 支持的来源

| 类别 | 来源 | 匹配方式 |
| --- | --- | --- |
| Qoder | Qoder（国内版 / 国际版） | 明文 `main.sqlite`，`chat_sessions.cwd` = 项目路径 |
| 本地 CLI | Claude Code、Codex CLI、Gemini CLI、Kimi Code、Copilot CLI | 项目路径或内容关键词 |
| 本地 CLI（轨迹/索引） | OpenClaw、ZCode | OpenClaw 会话 `cwd`、ZCode `tasks-index.sqlite` 的 `workspace_path` |
| 编辑器 | Cursor、Windsurf | workspace 路径 |
| 编辑器插件 | Copilot Chat（VS Code `github.copilot-chat`） | 会话 `cwd` / repository |
| 本地应用 | 豆包 Doubao、Chatbox、MiMo 小米、Marvis 腾讯、LM Studio | MiMo/Marvis 的目录字段或内容关键词 |
| 官方导出 | ChatGPT、Claude Web（需先导出 `conversations.json` 放到 Downloads） | 内容关键词 |

不支持：**Trae 本身**（SQLCipher 加密库，读不出也写不进）、Perplexity / 文心一言 / 通义千问（无本地结构化数据）。
每个来源的详细路径与可靠性见 [references/sources.md](references/sources.md)。

## 前置自检（开跑前必须做）

1. **确认 Python 可用**。优先系统 `python` / `python3`；Windows 上若没有，用 Trae 内置的解释器：
   `%APPDATA%\TRAE SOLO CN\ModularData\ai-agent\vm\tools\python\python.exe`。
   脚本只用标准库，无需安装依赖。
2. **确认目标项目标识**。用户给的是 GitHub URL / 仓库名 / 项目文件夹名 / 本地路径，任一即可。
   用户没说就根据当前打开的工程名推断，或直接问。
3. **确认输出目录**。默认放在当前工程下的 `.trae-import/`。
4. **全程只读来源数据**，不改动任何原始文件。若某来源不可读（未安装、加密、权限），如实汇报并跳过，不要闷头重试。

自检任一项不过，立即停下并告诉用户怎么解决。

## 工作流

脚本：`scripts/trae_migrate.py`（`<SKILL_DIR>` 指本技能目录）。

### 第 1 步 · 扫描

```bash
python "<SKILL_DIR>/scripts/trae_migrate.py" scan --project "<项目标识>" --out-dir ".trae-import"
```

- 想直接列全部会话（不筛选）：加 `--all`
- 只看某些来源：加 `--source "Cursor,Claude"`
- 结果会写入 `.trae-import/_scan.json`

把结果按下面的模板汇报给用户（**只用文字表格，别贴 JSON**）：

```
本地 AI 工具扫描结果（共探测 17 类来源）：

✅ Claude Code  — 共 17 个会话，匹配 12 个
✅ MiMo 小米    — 共 13 个会话，匹配 8 个
❌ Cursor       — 未安装 / 无可读数据
⚠️ ChatGPT      — 未找到导出文件（需先把官方导出放到 Downloads）

共找到 13 个相关会话：
  [ 1] Claude Code | 2026-08-10 | 1303 条 | 把 OpenClaw-CN 迁移到官方版 | 路径+内容匹配
  ...
```

然后**问用户要导出哪些**（序号，支持 `1,2,5` / `1-4` / `all`）。

### 第 2 步 · 导出

```bash
python "<SKILL_DIR>/scripts/trae_migrate.py" export --out-dir ".trae-import" --pick "1,2,5"
```

产物：

- `.trae-import/_migrate_export/<序号>-<标题>.md` —— 每个会话一份历史记录
- `.trae-import/_migrate_export/_index.md` —— 对照表 + 每个会话的**种子提示词**
- `.trae-import/_manifest.json` —— 已导出清单（用于幂等，重复导出前先看这里）

逐个报进度，别一次性静默完成。

### 第 3 步 · 收尾（关键：把"手动那一步"讲清楚）

告诉用户：

1. 打开 `.trae-import/_migrate_export/_index.md`，里面有每个会话的**种子提示词**。
2. 在 Trae 里**新建会话** → 整段粘贴种子提示词 → 发送。
3. Trae 会先 `Read` 那份历史 md，读完就带着完整上下文，之后正常接着聊。
4. 会话标题建议**从列表底部往上改**（改名会顶到最前，从下往上改不会乱）。
5. 全部确认没问题后，可以删掉 `.trae-import/`（纯临时产物）。

## 种子提示词长什么样

`export` 会自动生成，形如：

```text
这是我之前在 <来源工具> 里的对话历史，请先读取文件 <绝对路径> 作为上下文，
读完后基于该历史继续和我讨论。接下来我想说：
```

用户只要在末尾补上自己的下一句话即可。

## 幂等与安全

- 导出前置检查 `_manifest.json`：已导出过的会话提示用户，避免重复堆文件。
- **不改动**任何来源数据；SQLite 均以只读方式打开（先复制到临时目录再 `mode=ro`）。
- 不要迁移任何「记忆 / memory」，只迁对话正文。
- 汇报和文件里如出现 API Key、口令等敏感串，不要额外复述或广播给用户。

## 常见问题

- **某个来源是 0 个会话**：可能是关键词太窄、该工具还没用过，或数据在加密库里。换关键词或加 `--all` 再试。
- **Qoder 的对话**：可用。Qoder 国内版把会话存在 `%APPDATA%\com.qodercn.app.stable\main.sqlite`（明文 SQLite），读取 `chat_sessions` + `chat_session_messages` 即可；会话的 `cwd` 就是项目路径，匹配很准。
- **Cursor / Windsurf 读不到**：对话存在 `state.vscdb`（SQLite），不同版本字段名会变；若为 0，属于已知的"尽力而为"情况。
- **豆包 / Kimi / Copilot 结果不完整**：这些来源没有项目路径字段，只能靠内容关键词匹配，可能有漏网之鱼。
- **ChatGPT / Claude Web 读不到**：先到官方设置里导出数据，把 `conversations.json` 放到 `Downloads`，再重新扫描。
- **MiMo 小米（含 MiMo 桌面版）**：会话在 `%USERPROFILE%\.local\share\mimocode\mimocode.db`（明文 SQLite）。读 `session` + `message` + `part` 三张表拼接正文，`session.directory` 就是项目路径。
- **Marvis 腾讯**：会话在 `%USERPROFILE%\.marvis\database\data.db`（明文 SQLite）。读 `conversations` + `messages`（`message_seq` 排序）。
- **OpenClaw**：会话在 `%USERPROFILE%\.openclaw\agents\main\sessions\<uuid>.jsonl`，逐行 `message` 事件即正文；`session` 行的 `cwd` 是项目路径。`*.trajectory.jsonl` 是运行轨迹，正文不完整，会自动跳过。
- **ZCode**：会话在 `%USERPROFILE%\.zcode\cli\agents\<session>\agent_<id>\transcript.jsonl`；取最后一条 `model_request` 的 `payload.messages` 即完整对话。项目路径来自 `~/.zcode/v2/tasks-index.sqlite` 的 `workspace_path`。子代理（`subagent`）轨迹会跳过，避免重复。
- **LM Studio / Copilot Chat 读不到**：LM Studio 需 `~/.lmstudio/conversations/*.conversation.json`；Copilot Chat 的行可能都在 `session-store.db-wal` 里，脚本会连同 `-wal`/`-shm` 一起复制后再读，若仍为空说明该插件确实没用过。
- **想从 Trae 导出**：做不到，Trae 会话在加密库里。