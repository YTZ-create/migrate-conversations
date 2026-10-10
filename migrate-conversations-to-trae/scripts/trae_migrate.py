#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""trae_migrate.py

Scan local AI tools for past conversations, filter by a target project,
and export the selected ones to Markdown + ready-to-paste seed prompts
so they can be continued inside Trae.

Only the Python standard library is used. All reading of source data is
strictly read-only.

Subcommands
-----------
  scan   --project <name|path|url> [--out-dir DIR] [--source NAME] [--all] [--json]
  export --out-dir DIR --pick 1,2,3 [--scan FILE]
  sources

Example
-------
  python trae_migrate.py scan  --project my-repo --out-dir .trae-import
  python trae_migrate.py export --out-dir .trae-import --pick 1,2,5
"""

import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

HOME = Path.home()
APPDATA = Path(os.environ.get("APPDATA", str(HOME / "AppData" / "Roaming")))
LOCALAPPDATA = Path(os.environ.get("LOCALAPPDATA", str(HOME / "AppData" / "Local")))
DOWNLOADS = HOME / "Downloads"

MAX_CONVS_PER_SOURCE = 400          # safety cap
MAX_FILE_BYTES = 200 * 1024 * 1024  # skip absurdly large files

STOPWORDS = {
    "http", "https", "www", "com", "github", "git", "main", "master", "the",
    "and", "for", "with", "from", "app", "apps", "src", "dev", "code", "user",
    "users", "desktop", "documents", "downloads", "projects", "project",
}


# --------------------------------------------------------------------------
# generic helpers
# --------------------------------------------------------------------------
def norm(p):
    """Normalize a filesystem path-ish string for comparison."""
    if not p:
        return ""
    s = str(p).strip().strip('"').strip("'")
    s = s.replace("\\", "/")
    s = re.sub(r"^file:///", "", s, flags=re.I)
    s = re.sub(r"^[a-zA-Z]:", "", s)
    s = s.replace("//", "/")
    s = s.rstrip("/")
    return s.lower()


def enc_path(p):
    """Claude-Code style path encoding: every : \\ / becomes '-'."""
    if not p:
        return ""
    s = str(p).replace("\\", "-").replace("/", "-").replace(":", "-")
    return re.sub(r"-+", "-", s).strip("-").lower()


def tokens_of(s):
    toks = re.findall(r"[a-z0-9]+", str(s).lower())
    toks = [t for t in toks if len(t) >= 3 and t not in STOPWORDS]
    if not toks:
        toks = [str(s).strip().lower()]
    seen, out = set(), []
    for t in toks:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def safe_read_text(path):
    try:
        if os.path.getsize(path) > MAX_FILE_BYTES:
            return ""
        with open(path, "rb") as f:
            raw = f.read()
        for enc in ("utf-8", "utf-8-sig", "gbk", "latin-1"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", "replace")
    except Exception:
        return ""


def read_jsonl(path):
    out = []
    txt = safe_read_text(path)
    if not txt:
        return out
    for line in txt.splitlines():
        line = line.strip().rstrip(",")
        if not line or line in ("[", "]"):
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            out.append(obj)
        elif isinstance(obj, list):
            out.extend([o for o in obj if isinstance(o, dict)])
    return out


def read_json_maybe(path):
    txt = safe_read_text(path)
    if not txt:
        return None
    txt = txt.strip()
    if not txt:
        return None
    try:
        return json.loads(txt)
    except Exception:
        pass
    # tolerate jsonl / concatenated json
    starts = [m.start() for m in re.finditer(r"^[\[{]", txt, flags=re.M)]
    if len(starts) > 1:
        return None
    try:
        return json.loads("[" + txt.replace("}\n{", "},{") + "]")
    except Exception:
        return None


def ts_to_str(v):
    """Best-effort conversion of a timestamp to 'YYYY-MM-DD HH:MM'."""
    if v is None:
        return ""
    if isinstance(v, str):
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})", v)
        if m:
            return "%s-%s-%s %s:%s" % m.groups()
        return v[:19]
    try:
        f = float(v)
    except Exception:
        return ""
    if f > 1e12:  # ms
        f = f / 1000.0
    if f <= 0 or f > 4e9:
        return ""
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(f))
    except Exception:
        return ""


def content_to_text(content):
    """Flatten a message 'content' field into plain text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    parts = []
    if isinstance(content, list):
        for b in content:
            if isinstance(b, str):
                parts.append(b)
            elif isinstance(b, dict):
                t = b.get("type")
                if t in (None, "text", "input_text", "output_text", "text_delta"):
                    for k in ("text", "content", "value"):
                        v = b.get(k)
                        if isinstance(v, str) and v.strip():
                            parts.append(v)
                            break
                elif t == "tool_use":
                    parts.append("[工具调用: %s]" % b.get("name", "?"))
                elif t == "image" or t == "input_image":
                    parts.append("[图片]")
                # tool_result is intentionally dropped (noise)
    elif isinstance(content, dict):
        for k in ("text", "content", "value"):
            v = content.get(k)
            if isinstance(v, str):
                parts.append(v)
                break
    return "\n".join(p for p in parts if p and p.strip()).strip()


ROLE_MAP = {
    "user": "user", "human": "user", "me": "user", "customer": "user",
    "assistant": "assistant", "ai": "assistant", "bot": "assistant",
    "model": "assistant", "gemini": "assistant", "agent": "assistant",
    "system": "system", "tool": "tool",
}
TEXT_KEYS = ("text", "content", "message", "contentText", "richText", "body", "value")


def as_message(d):
    """Return (role, text) if dict looks like a chat message, else None."""
    if not isinstance(d, dict):
        return None
    role = None
    for k in ("role", "sender", "speaker", "from", "author"):
        v = d.get(k)
        if isinstance(v, str) and v.lower() in ROLE_MAP:
            role = ROLE_MAP[v.lower()]
            break
        if isinstance(v, dict):
            r = v.get("role")
            if isinstance(r, str) and r.lower() in ROLE_MAP:
                role = ROLE_MAP[r.lower()]
                break
    if role is None:
        return None
    txt = ""
    for k in TEXT_KEYS:
        if k in d and d[k] is not None:
            txt = content_to_text(d[k])
            if txt:
                break
    if not txt:
        return None
    return (role, txt)


def walk_messages(obj, acc):
    """Recursively collect message-like dicts preserving encounter order."""
    if isinstance(obj, list):
        for it in obj:
            walk_messages(it, acc)
    elif isinstance(obj, dict):
        m = as_message(obj)
        if m:
            acc.append(m)
            # still descend: some tools nest replies
        for k, v in obj.items():
            if k in TEXT_KEYS:
                continue
            if isinstance(v, (list, dict)):
                walk_messages(v, acc)


def generic_messages(obj):
    acc = []
    walk_messages(obj, acc)
    return acc


def new_conv(source, cid, title, messages, created="", updated="", project=None, path="", note=""):
    return {
        "source": source,
        "id": str(cid),
        "title": (title or "").strip() or "(无标题)",
        "messages": messages,
        "created": created,
        "updated": updated,
        "project": project,
        "path": str(path),
        "note": note,
    }


TAG_RE = re.compile(r"<[^>]+>")
NOISE_BLOCK_RE = [
    re.compile(r"<ide_opened_file>.*?</ide_opened_file>", re.S | re.I),
    re.compile(r"<ide_selection>.*?</ide_selection>", re.S | re.I),
    re.compile(r"<system-reminder>.*?</system-reminder>", re.S | re.I),
]


def clean_title(text):
    t = TAG_RE.sub(" ", text or "")
    t = re.sub(r"\s+", " ", t).strip(" 　-—:：")
    return t[:60]


def strip_noise(text):
    t = text or ""
    for rx in NOISE_BLOCK_RE:
        t = rx.sub(" ", t)
    t = re.sub(r"[ \t]+\n", "\n", t)
    return t.strip()


def finalize(conv):
    """Drop system noise, trim, keep only if it has real content."""
    msgs = []
    for role, text in conv.get("messages", []):
        if role == "system":
            continue
        text = strip_noise(text)
        if not text:
            continue
        msgs.append({"role": role, "text": text})
    conv["messages"] = msgs
    if not conv.get("title") or conv["title"] == "(无标题)":
        for m in msgs:
            if m["role"] == "user":
                t = clean_title(m["text"])
                if t:
                    conv["title"] = t
                    break
    else:
        conv["title"] = clean_title(conv["title"])
    return conv


def open_sqlite_ro(path):
    """Open a possibly-locked SQLite db read-only (copy first, then ro)."""
    tmp = None
    try:
        tmp = Path(tempfile.gettempdir()) / ("trae_probe_%d.db" % (abs(hash(str(path))) % 10 ** 9))
        shutil.copy2(str(path), str(tmp))
        con = sqlite3.connect("file:%s?mode=ro" % tmp.as_posix(), uri=True)
        return con
    except Exception:
        pass
    try:
        con = sqlite3.connect("file:%s?mode=ro&immutable=1" % Path(path).as_posix(), uri=True)
        return con
    except Exception:
        return None


def table_names(con):
    try:
        return [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    except Exception:
        return []


def kv_rows(con, table, key_col, val_col, like=None):
    try:
        q = "SELECT %s, %s FROM %s" % (key_col, val_col, table)
        if like:
            q += " WHERE %s LIKE ?" % key_col
            cur = con.execute(q, (like,))
        else:
            cur = con.execute(q)
        return cur.fetchall()
    except Exception:
        return []


# --------------------------------------------------------------------------
# adapters
# --------------------------------------------------------------------------
def scan_claude_code():
    """~/.claude/projects/<encoded-cwd>/*.jsonl"""
    convs = []
    root = HOME / ".claude" / "projects"
    if not root.is_dir():
        return convs
    for proj_dir in sorted(root.iterdir()):
        if not proj_dir.is_dir():
            continue
        for f in sorted(proj_dir.glob("*.jsonl")):
            rows = read_jsonl(f)
            if not rows:
                continue
            cwd = ""
            sid = ""
            created = updated = ""
            summary = ""
            msgs = []
            for r in rows:
                if not cwd and isinstance(r.get("cwd"), str):
                    cwd = r["cwd"]
                if not sid and isinstance(r.get("sessionId"), str):
                    sid = r["sessionId"]
                tt = ts_to_str(r.get("timestamp"))
                if tt:
                    created = created or tt
                    updated = tt
                t = r.get("type")
                if t == "summary" and isinstance(r.get("summary"), str):
                    summary = r["summary"]
                    continue
                if t not in ("user", "assistant"):
                    continue
                if r.get("isSidechain") is True:
                    continue
                msg = r.get("message") or {}
                role = msg.get("role") or t
                role = ROLE_MAP.get(str(role).lower())
                if role not in ("user", "assistant"):
                    continue
                txt = content_to_text(msg.get("content"))
                if not txt:
                    continue
                msgs.append((role, txt))
            conv = new_conv("Claude Code", sid or f.stem, summary, msgs,
                            created, updated, cwd, f)
            convs.append(finalize(conv))
    return convs


def scan_codex():
    """~/.codex/sessions/YYYY/MM/DD/*.jsonl  (also legacy history.jsonl)"""
    convs = []
    root = HOME / ".codex" / "sessions"
    files = []
    if root.is_dir():
        files += sorted(root.rglob("*.jsonl"))
    old = HOME / ".codex" / "history.jsonl"
    if old.is_file():
        files.append(old)
    for f in files[:MAX_CONVS_PER_SOURCE]:
        rows = read_jsonl(f)
        if not rows:
            continue
        cwd = sid = ""
        created = updated = ""
        ev, resp = [], []
        for r in rows:
            pl = r.get("payload") if isinstance(r.get("payload"), dict) else {}
            if r.get("type") == "session_meta":
                cwd = pl.get("cwd") or cwd
                sid = pl.get("id") or sid
                created = created or ts_to_str(r.get("timestamp"))
            tt = ts_to_str(r.get("timestamp"))
            if tt:
                updated = tt
            if r.get("type") == "event_msg":
                pt = pl.get("type")
                if pt == "user_message" and isinstance(pl.get("message"), str):
                    ev.append(("user", pl["message"]))
                elif pt == "agent_message" and isinstance(pl.get("message"), str):
                    ev.append(("assistant", pl["message"]))
            elif r.get("type") == "response_item" and pl.get("type") == "message":
                role = ROLE_MAP.get(str(pl.get("role", "")).lower())
                txt = content_to_text(pl.get("content"))
                if role and txt:
                    resp.append((role, txt))
            elif r.get("type") in ("user", "assistant") and isinstance(r.get("message"), dict):
                pass
        msgs = ev if ev else resp
        conv = new_conv("Codex CLI", sid or f.stem, "", msgs, created, updated, cwd, f)
        convs.append(finalize(conv))
    return convs


def scan_gemini():
    """~/.gemini/tmp/<hash>/chats/session-*.json  (falls back to history)"""
    convs = []
    root = HOME / ".gemini"
    if not root.is_dir():
        return convs
    for f in sorted(root.rglob("chats/session-*.json")):
        obj = read_json_maybe(f)
        if not isinstance(obj, dict):
            continue
        msgs = []
        for m in obj.get("messages", []) or []:
            role = ROLE_MAP.get(str(m.get("type") or m.get("role") or "").lower())
            txt = content_to_text(m.get("content"))
            if role and txt:
                msgs.append((role, txt))
        if not msgs:
            msgs = generic_messages(obj)
        project = None
        pr = f.parent.parent / ".project_root"
        if pr.is_file():
            project = safe_read_text(pr).strip()
        conv = new_conv("Gemini CLI", f.stem, "", msgs,
                        ts_to_str(obj.get("startTime")), ts_to_str(obj.get("lastUpdated")),
                        project, f)
        convs.append(finalize(conv))
    # legacy logs.json
    for f in sorted(root.rglob("logs.json"))[:50]:
        obj = read_json_maybe(f)
        if isinstance(obj, list):
            msgs = generic_messages(obj)
            if msgs:
                convs.append(finalize(new_conv("Gemini CLI", str(f), "", msgs,
                                               project=str(f.parent), path=f)))
    return convs


def scan_kimi():
    """~/.kimi-code/  (format varies; best-effort)"""
    convs = []
    root = HOME / ".kimi-code"
    if not root.is_dir():
        return convs
    for f in sorted(list(root.rglob("*.jsonl")) + list(root.rglob("*.json")))[:MAX_CONVS_PER_SOURCE]:
        if f.stat().st_size == 0:
            continue
        rows = read_jsonl(f)
        if not rows:
            obj = read_json_maybe(f)
            rows = generic_messages(obj) if obj is not None else []
            if rows:
                convs.append(finalize(new_conv("Kimi Code", f.stem, "", rows, project=str(f.parent), path=f)))
            continue
        msgs = generic_messages(rows)
        if msgs:
            convs.append(finalize(new_conv("Kimi Code", f.stem, "", msgs, project=str(f.parent), path=f)))
    return convs


def scan_copilot():
    """~/.copilot/session-state/  (SQLite or JSONL; best-effort)"""
    convs = []
    root = HOME / ".copilot" / "session-state"
    if not root.is_dir():
        root = HOME / ".copilot"
    if not root.is_dir():
        return convs
    for f in sorted(list(root.rglob("*.jsonl")))[:MAX_CONVS_PER_SOURCE]:
        rows = read_jsonl(f)
        msgs = generic_messages(rows)
        if msgs:
            convs.append(finalize(new_conv("Copilot CLI", f.stem, "", msgs, project=str(f.parent), path=f)))
    for f in sorted(list(root.rglob("*.db")) + list(root.rglob("*.sqlite")))[:20]:
        con = open_sqlite_ro(f)
        if not con:
            continue
        try:
            for t in table_names(con):
                cols = _cols(con, t)
                if "key" in cols and "value" in cols:
                    for k, v in kv_rows(con, t, "key", "value"):
                        try:
                            data = json.loads(v) if isinstance(v, (str, bytes)) else v
                        except Exception:
                            continue
                        msgs = generic_messages(data)
                        if len(msgs) >= 2:
                            convs.append(finalize(new_conv(
                                "Copilot CLI", str(k), "", msgs, project=str(f.parent), path=f)))
        finally:
            con.close()
    return convs


def _cols(con, table):
    try:
        return [r[1] for r in con.execute("PRAGMA table_info(%s)" % table)]
    except Exception:
        return []


def _workspace_folder(ws_dir):
    wj = ws_dir / "workspace.json"
    obj = read_json_maybe(wj)
    if isinstance(obj, dict):
        return obj.get("folder") or obj.get("workspace") or ""
    return ""


def _cursor_like(root, source_name, kv_table, key_col="key", val_col="value",
                 composer_like="composerData:%", bubble_like="bubbleId:%"):
    """Shared reader for Cursor / Windsurf style workspaceStorage."""
    convs = []
    if not root.is_dir():
        return convs
    for ws in sorted(root.iterdir()):
        db = ws / "state.vscdb"
        if not db.is_file():
            continue
        project = _workspace_folder(ws)
        con = open_sqlite_ro(db)
        if not con:
            continue
        try:
            if kv_table not in table_names(con):
                continue
            # composer metadata
            composers = {}
            for k, v in kv_rows(con, kv_table, key_col, val_col, composer_like):
                try:
                    data = json.loads(v) if isinstance(v, (str, bytes)) else v
                except Exception:
                    continue
                if isinstance(data, dict):
                    composers[str(k).split(":", 1)[1]] = data

            bubbles = {}
            for k, v in kv_rows(con, kv_table, key_col, val_col, bubble_like):
                try:
                    data = json.loads(v) if isinstance(v, (str, bytes)) else v
                except Exception:
                    continue
                if not isinstance(data, dict):
                    continue
                parts = str(k).split(":")
                if len(parts) < 3:
                    continue
                comp_id = parts[1]
                bubbles.setdefault(comp_id, []).append(data)

            for comp_id, meta in composers.items():
                order = meta.get("fullConversationHeadersOnly") or []
                msgs = []
                if order:
                    by_id = {}
                    for b in bubbles.get(comp_id, []):
                        bid = b.get("bubbleId") or b.get("id")
                        if bid:
                            by_id[str(bid)] = b
                    for h in order:
                        bid = str(h.get("bubbleId") or "")
                        b = by_id.get(bid)
                        if not b:
                            continue
                        t = b.get("type") if b.get("type") is not None else h.get("type")
                        role = "user" if t == 1 else ("assistant" if t == 2 else None)
                        txt = content_to_text(b.get("text") or b.get("richText"))
                        if role and txt:
                            msgs.append((role, txt))
                if not msgs:
                    for b in sorted(bubbles.get(comp_id, []), key=lambda x: x.get("createdAt") or 0):
                        t = b.get("type")
                        role = "user" if t == 1 else ("assistant" if t == 2 else None)
                        txt = content_to_text(b.get("text") or b.get("richText"))
                        if role and txt:
                            msgs.append((role, txt))
                if not msgs:
                    continue
                title = meta.get("name") or ""
                conv = new_conv(source_name, comp_id, title, msgs,
                                ts_to_str(meta.get("createdAt")), ts_to_str(meta.get("lastUpdatedAt") or meta.get("updatedAt")),
                                project, db)
                convs.append(finalize(conv))
        finally:
            con.close()
    return convs


def scan_cursor():
    return _cursor_like(APPDATA / "Cursor" / "User" / "workspaceStorage",
                        "Cursor", "cursorDiskKV")


def scan_windsurf():
    """Windsurf keeps chat inside ItemTable (key contains 'chatdata'/'aichat')."""
    convs = []
    for base in (APPDATA / "Windsurf" / "User" / "workspaceStorage",
                 APPDATA / "Windsurf" / "User" / "globalStorage"):
        if not base.is_dir():
            continue
        for ws in sorted(base.iterdir()):
            db = ws / "state.vscdb" if (ws / "state.vscdb").is_file() else None
            if not db and ws.is_file() and ws.suffix == ".vscdb":
                db = ws
            if not db:
                continue
            project = _workspace_folder(ws) if ws.is_dir() else ""
            con = open_sqlite_ro(db)
            if not con:
                continue
            try:
                tables = table_names(con)
                for t in tables:
                    cols = _cols(con, t)
                    if "key" not in cols or "value" not in cols:
                        continue
                    for k, v in kv_rows(con, t, "key", "value"):
                        ks = str(k).lower()
                        if not any(w in ks for w in ("chatdata", "aichat", "cascade", "chat")):
                            continue
                        try:
                            data = json.loads(v) if isinstance(v, (str, bytes)) else v
                        except Exception:
                            continue
                        msgs = generic_messages(data)
                        if len(msgs) >= 2:
                            convs.append(finalize(new_conv(
                                "Windsurf", str(k), "", msgs, project=project, path=db)))
            finally:
                con.close()
    return convs


def scan_doubao():
    """Doubao: %LOCALAPPDATA%/Doubao/**/trajectory.jsonl (best-effort)."""
    convs = []
    roots = [LOCALAPPDATA / "Doubao", APPDATA / "Doubao",
             LOCALAPPDATA / "ByteDance" / "Doubao"]
    files = []
    for r in roots:
        if r.is_dir():
            files += sorted(r.rglob("trajectory.jsonl"))
    for f in files[:MAX_CONVS_PER_SOURCE]:
        rows = read_jsonl(f)
        if not rows:
            continue
        msgs = generic_messages(rows)
        if not msgs:
            continue
        convs.append(finalize(new_conv("豆包 Doubao", str(f.relative_to(f.anchor)),
                                       "", msgs,
                                       project=str(f.parent), path=f, note="基于内容关键词匹配，可能不完整")))
    return convs


def scan_chatbox():
    """Chatbox: %APPDATA%/xyz.chatboxapp.app/config.json"""
    convs = []
    cands = [
        APPDATA / "xyz.chatboxapp.app" / "config.json",
        APPDATA / "xyz.chatboxapp.ce" / "config.json",
        APPDATA / "Chatbox" / "config.json",
        LOCALAPPDATA / "xyz.chatboxapp.app" / "config.json",
    ]
    for f in cands:
        if not f.is_file():
            continue
        obj = read_json_maybe(f)
        if not isinstance(obj, dict):
            continue
        store = obj.get("conversations") or obj.get("sessions") or {}
        items = store.values() if isinstance(store, dict) else store
        for item in items:
            if not isinstance(item, dict):
                continue
            msgs = []
            for m in (item.get("messages") or item.get("chatMessages") or []):
                m = m if isinstance(m, dict) else {}
                role = ROLE_MAP.get(str(m.get("role", "")).lower())
                txt = content_to_text(m.get("content"))
                if role and txt:
                    msgs.append((role, txt))
            if not msgs:
                continue
            convs.append(finalize(new_conv(
                "Chatbox", item.get("id", ""), item.get("name") or item.get("topic") or "",
                msgs, ts_to_str(item.get("createdAt")), ts_to_str(item.get("updatedAt")), None, f)))
    return convs


def _find_download_jsons():
    out = []
    for d in (DOWNLOADS, HOME / "Desktop"):
        if not d.is_dir():
            continue
        for f in sorted(d.glob("conversations.json")):
            out.append(f)
        for zdir in sorted(d.glob("*/conversations.json")):
            out.append(zdir)
    return out


def _chatgpt_linearize(conv):
    mapping = conv.get("mapping") or {}
    root = None
    for nid, node in mapping.items():
        if not isinstance(node, dict):
            continue
        if node.get("parent") in (None, "") or node.get("parent") not in mapping:
            root = node
            break
    msgs = []
    if root is not None:
        node = root
        guard = 0
        while node and guard < 100000:
            guard += 1
            m = node.get("message")
            if isinstance(m, dict):
                role = ROLE_MAP.get(str((m.get("author") or {}).get("role", "")).lower())
                txt = content_to_text((m.get("content") or {}).get("parts"))
                if role in ("user", "assistant") and txt:
                    msgs.append((role, txt))
            kids = node.get("children") or []
            nxt = None
            for cid in kids:
                c = mapping.get(cid)
                if c:
                    nxt = c
                    break
            node = nxt
    return msgs


def scan_official_exports():
    convs = []
    for f in _find_download_jsons():
        obj = read_json_maybe(f)
        if not isinstance(obj, list):
            continue
        for item in obj:
            if not isinstance(item, dict):
                continue
            if "chat_messages" in item:  # Claude Web export
                msgs = []
                for m in item.get("chat_messages") or []:
                    role = ROLE_MAP.get(str(m.get("sender", "")).lower())
                    txt = content_to_text(m.get("text"))
                    if role and txt:
                        msgs.append((role, txt))
                if msgs:
                    convs.append(finalize(new_conv(
                        "Claude Web", item.get("uuid", ""), item.get("name", ""),
                        msgs, ts_to_str(item.get("created_at")), ts_to_str(item.get("updated_at")), None, f)))
            elif "mapping" in item:  # ChatGPT export
                msgs = _chatgpt_linearize(item)
                if msgs:
                    convs.append(finalize(new_conv(
                        "ChatGPT", item.get("id", ""), item.get("title", ""),
                        msgs, ts_to_str(item.get("create_time")), ts_to_str(item.get("update_time")), None, f)))
    return convs


def _qoder_db_paths():
    """Locate Qoder's plaintext chat store (main.sqlite)."""
    cands = [
        APPDATA / "com.qodercn.app.stable" / "main.sqlite",
        APPDATA / "Qoder" / "main.sqlite",
        APPDATA / "Qoder CN" / "main.sqlite",
        LOCALAPPDATA / "Qoder CN" / "main.sqlite",
        LOCALAPPDATA / "Qoder" / "main.sqlite",
        HOME / ".qoder-cn" / "main.sqlite",
        HOME / ".qoder" / "main.sqlite",
    ]
    for base in (APPDATA, LOCALAPPDATA):
        try:
            for d in base.iterdir():
                if d.is_dir() and "qoder" in d.name.lower() and (d / "main.sqlite").is_file():
                    cands.append(d / "main.sqlite")
        except Exception:
            pass
    seen, out = set(), []
    for p in cands:
        if p.is_file():
            k = str(p).lower()
            if k not in seen:
                seen.add(k)
                out.append(p)
    return out


def scan_qoder():
    """Qoder: main.sqlite -> chat_sessions + chat_session_messages (plaintext SQLite)."""
    convs = []
    for db in _qoder_db_paths():
        con = open_sqlite_ro(db)
        if not con:
            continue
        try:
            tables = table_names(con)
            if "chat_sessions" not in tables or "chat_session_messages" not in tables:
                continue
            by_sid = {}
            try:
                for sid, _seq, pj in con.execute(
                        "SELECT session_id, sequence, payload_json "
                        "FROM chat_session_messages ORDER BY session_id, sequence"):
                    if not isinstance(pj, (str, bytes)):
                        continue
                    try:
                        d = json.loads(pj)
                    except Exception:
                        continue
                    if not isinstance(d, dict) or d.get("subtype") == "hook_activity":
                        continue
                    role = ROLE_MAP.get(str(d.get("role", "")).lower())
                    if role not in ("user", "assistant"):
                        continue
                    txt = content_to_text(d.get("text"))
                    if not txt:
                        continue
                    by_sid.setdefault(sid, []).append((role, txt))
            except Exception:
                pass

            try:
                rows = con.execute(
                    "SELECT session_id, title, cwd, created_at, updated_at, archived, deleted_at "
                    "FROM chat_sessions").fetchall()
            except Exception:
                rows = []
            for sid, title, cwd, created, updated, archived, deleted in rows:
                if deleted or archived in (1, True):
                    continue
                msgs = by_sid.get(sid, [])
                if not msgs:
                    continue
                convs.append(finalize(new_conv(
                    "Qoder", sid, title, msgs,
                    ts_to_str(created), ts_to_str(updated), cwd, db)))
        finally:
            con.close()
    return convs


def _open_sqlite_with_wal(path):
    """Open a SQLite db read-only together with its -wal/-shm side files.

    Some apps (e.g. Copilot Chat) keep all rows in the WAL, so copying only
    the main .db would lose the data. We copy the trio into a temp dir.
    """
    base = Path(path)
    tmpdir = Path(tempfile.gettempdir()) / ("trae_wal_%d" % (abs(hash(str(base))) % 10 ** 9))
    try:
        if tmpdir.exists():
            shutil.rmtree(str(tmpdir), ignore_errors=True)
        tmpdir.mkdir(parents=True, exist_ok=True)
        for suffix in ("", "-wal", "-shm"):
            src = Path(str(base) + suffix)
            if src.is_file():
                shutil.copy2(str(src), str(tmpdir / (base.name + suffix)))
        return sqlite3.connect("file:%s?mode=ro" % (tmpdir / base.name).as_posix(), uri=True)
    except Exception:
        return None


def _find_dbs(names, roots, max_depth=4):
    """Locate db files by basename under the given roots (os.walk, pruned)."""
    out, seen = [], set()
    for root in roots:
        if not root.is_dir():
            continue
        base_depth = len(str(root).rstrip("\\/").split(os.sep))
        try:
            for dirpath, dirnames, filenames in os.walk(str(root)):
                depth = len(dirpath.rstrip("\\/").split(os.sep)) - base_depth
                if depth >= max_depth:
                    dirnames[:] = []
                    continue
                dirnames[:] = [d for d in dirnames if d not in ("node_modules", ".git", "Cache", "GPUCache")]
                for fn in filenames:
                    if fn.lower() in names:
                        p = Path(dirpath) / fn
                        try:
                            if p.stat().st_size <= 4096:
                                continue
                        except Exception:
                            continue
                        k = str(p).lower()
                        if k not in seen:
                            seen.add(k)
                            out.append(p)
        except Exception:
            continue
    return out


def _mimo_db_paths():
    cands = [
        HOME / ".local" / "share" / "mimocode" / "mimocode.db",
        HOME / ".config" / "mimocode" / "mimocode.db",
        HOME / ".mimocode" / "mimocode.db",
    ]
    # shallow sweep of likely parents only (never the whole HOME)
    for base in (HOME / ".local" / "share", HOME / ".config", HOME / "AppData" / "Roaming", HOME / "AppData" / "Local"):
        cands += _find_dbs({"mimocode.db"}, [base])
    seen, out = set(), []
    for p in cands:
        if p.is_file():
            k = str(p).lower()
            if k not in seen:
                seen.add(k)
                out.append(p)
    return out


def scan_mimo():
    """MiMo / MiMo Desktop: mimocode.db -> session + message + part (plaintext SQLite)."""
    convs = []
    for db in _mimo_db_paths():
        con = open_sqlite_ro(db)
        if not con:
            continue
        try:
            tables = table_names(con)
            if not {"session", "message", "part"} <= set(tables):
                continue
            parts = {}
            try:
                for mid, pdata in con.execute(
                        "SELECT message_id, data FROM part ORDER BY time_created"):
                    if not isinstance(pdata, (str, bytes)):
                        continue
                    try:
                        d = json.loads(pdata)
                    except Exception:
                        continue
                    if isinstance(d, dict) and d.get("type") == "text":
                        t = content_to_text(d.get("text"))
                        if t:
                            parts.setdefault(mid, []).append(t)
            except Exception:
                pass
            by_sid = {}
            try:
                for mid, sid, mdata in con.execute(
                        "SELECT id, session_id, data FROM message ORDER BY time_created"):
                    try:
                        d = json.loads(mdata) if isinstance(mdata, (str, bytes)) else {}
                    except Exception:
                        d = {}
                    role = ROLE_MAP.get(str((d or {}).get("role", "")).lower())
                    if role not in ("user", "assistant"):
                        continue
                    txt = "\n".join(parts.get(mid, []))
                    if not txt:
                        continue
                    by_sid.setdefault(sid, []).append((role, txt))
            except Exception:
                pass
            try:
                rows = con.execute(
                    "SELECT id, title, directory, time_created, time_updated FROM session").fetchall()
            except Exception:
                rows = []
            for sid, title, directory, tc, tu in rows:
                msgs = by_sid.get(sid, [])
                if not msgs:
                    continue
                convs.append(finalize(new_conv(
                    "MiMo 小米", sid, title, msgs,
                    ts_to_str(tc), ts_to_str(tu), directory, db)))
        finally:
            con.close()
    return convs


def scan_marvis():
    """Tencent Marvis: ~/.marvis/database/data.db -> conversations + messages."""
    convs = []
    for db in [HOME / ".marvis" / "database" / "data.db", HOME / ".marvis" / "data.db"]:
        if not db.is_file():
            continue
        con = open_sqlite_ro(db)
        if not con:
            continue
        try:
            tables = table_names(con)
            if "conversations" not in tables or "messages" not in tables:
                continue
            by_cid = {}
            try:
                for cid, role, content in con.execute(
                        "SELECT conversation_id, role, content FROM messages "
                        "ORDER BY conversation_id, message_seq"):
                    r = ROLE_MAP.get(str(role).lower())
                    if r not in ("user", "assistant"):
                        continue
                    txt = content_to_text(content)
                    if not txt:
                        continue
                    by_cid.setdefault(cid, []).append((r, txt))
            except Exception:
                pass
            try:
                rows = con.execute(
                    "SELECT conversation_id, title, created_at, updated_at FROM conversations").fetchall()
            except Exception:
                rows = []
            for cid, title, created, updated in rows:
                msgs = by_cid.get(cid, [])
                if not msgs:
                    continue
                convs.append(finalize(new_conv(
                    "Marvis 腾讯", cid, title, msgs,
                    ts_to_str(created), ts_to_str(updated), None, db)))
        finally:
            con.close()
    return convs


def _lmstudio_dirs():
    cands = [
        HOME / ".lmstudio" / "conversations",
        HOME / ".cache" / "lm-studio" / "conversations",
        HOME / ".cache" / "lmstudio" / "conversations",
    ]
    for base in (APPDATA, LOCALAPPDATA):
        cands.append(base / "LM Studio" / "conversations")
    return [c for c in cands if c.is_dir()]


def _lmstudio_text(version):
    if not isinstance(version, dict):
        return ""
    parts = [content_to_text(version.get("content"))]
    for step in version.get("steps") or []:
        if isinstance(step, dict):
            parts.append(content_to_text(step.get("content")))
    return "\n".join(p for p in parts if p and p.strip()).strip()


def scan_lmstudio():
    """LM Studio: ~/.lmstudio/conversations/*.conversation.json"""
    convs = []
    for base in _lmstudio_dirs():
        for f in sorted(base.glob("*.json")):
            d = read_json_maybe(f)
            if not isinstance(d, dict) or not isinstance(d.get("messages"), list):
                continue
            msgs = []
            for item in d.get("messages") or []:
                if not isinstance(item, dict):
                    continue
                versions = item.get("versions") or []
                sel = item.get("currentlySelected") or 0
                v = None
                if isinstance(versions, list) and versions:
                    v = versions[sel] if 0 <= sel < len(versions) else versions[0]
                if not isinstance(v, dict):
                    continue
                role = ROLE_MAP.get(str(v.get("role", "")).lower())
                if role not in ("user", "assistant"):
                    continue
                txt = _lmstudio_text(v)
                if txt:
                    msgs.append((role, txt))
            if msgs:
                convs.append(finalize(new_conv(
                    "LM Studio", f.stem, d.get("name", ""), msgs,
                    ts_to_str(d.get("createdAt")), ts_to_str(d.get("userLastMessagedAt")), None, f)))
    return convs


def _openclaw_sessions():
    dirs = [HOME / ".openclaw" / "agents" / "main" / "sessions"]
    for base in (HOME / "openclaw-backup", HOME / ".openclaw-profiles"):
        if base.is_dir():
            try:
                dirs.extend([p for p in base.rglob("sessions") if p.is_dir()])
            except Exception:
                pass
    out = []
    for d in dirs:
        try:
            out.extend(sorted(d.glob("*.jsonl")))
        except Exception:
            pass
    return out


def scan_openclaw():
    """OpenClaw: agents/main/sessions/<uuid>.jsonl (message events)."""
    convs, seen = [], set()
    for f in _openclaw_sessions():
        if f.name.endswith(".trajectory.jsonl"):
            continue
        key = f.stem
        if key in seen:
            continue
        seen.add(key)
        rows = read_jsonl(f)
        if not rows:
            continue
        project, msgs = None, []
        for r in rows:
            t = r.get("type")
            if t == "session":
                project = r.get("cwd") or project
            elif t == "message":
                m = r.get("message")
                if isinstance(m, dict):
                    role = ROLE_MAP.get(str(m.get("role", "")).lower())
                    if role not in ("user", "assistant"):
                        continue
                    txt = content_to_text(m.get("content"))
                    if txt:
                        msgs.append((role, txt))
        if msgs:
            convs.append(finalize(new_conv("OpenClaw", key, "", msgs, "", "", project, f)))
    return convs


def _zcode_tasks():
    """task_id -> (title, workspace_path) from ~/.zcode/v2/tasks-index.sqlite."""
    m = {}
    db = HOME / ".zcode" / "v2" / "tasks-index.sqlite"
    if not db.is_file():
        return m
    con = open_sqlite_ro(db)
    if not con:
        return m
    try:
        for tid, title, wsp in con.execute("SELECT task_id, title, workspace_path FROM tasks"):
            if tid:
                m[str(tid)] = (title, wsp)
    except Exception:
        pass
    finally:
        con.close()
    return m


def _zcode_extract(f):
    """Return (messages, last_len) from one agent transcript (or None)."""
    rows = read_jsonl(f)
    if not rows:
        return None
    last_msgs = None
    stream = {}  # assistantMessageId -> assembled non-reasoning text
    for r in rows:
        t = r.get("type")
        if t == "model_request":
            mm = (r.get("payload") or {}).get("messages")
            if isinstance(mm, list) and mm:
                last_msgs = mm
        elif t == "model_streaming":
            p = r.get("payload") or {}
            kind = str(p.get("kind") or "")
            d = p.get("delta")
            if isinstance(d, str) and d and "reason" not in kind and kind not in ("start", "done"):
                mid = p.get("assistantMessageId") or "_"
                stream[mid] = stream.get(mid, "") + d
    if not last_msgs:
        return None
    msgs = []
    for m in last_msgs:
        if not isinstance(m, dict):
            continue
        role = ROLE_MAP.get(str(m.get("role", "")).lower())
        if role not in ("user", "assistant"):
            continue
        txt = content_to_text(m.get("content"))
        if txt:
            msgs.append((role, txt))
    # assistant text often lives only in streaming deltas (tool-heavy turns)
    if not any(r == "assistant" for r, _ in msgs):
        for _mid, txt in stream.items():
            txt = txt.strip()
            if txt:
                msgs.append(("assistant", txt))
    return (msgs, len(last_msgs))


def scan_zcode():
    """ZCode CLI: ~/.zcode/cli/agents/<sess>/agent_<id>/transcript.jsonl

    A session may have several agent transcripts (sub-agents). We group by
    session and keep the transcript with the richest history, since each
    transcript records the whole accumulated context in model_request.
    Sub-agent-only sessions (delegated task, no human text) still surface but
    with little natural text, which is honest.
    """
    convs = []
    taskmap = _zcode_tasks()
    base = HOME / ".zcode" / "cli" / "agents"
    files = []
    if base.is_dir():
        try:
            files = sorted(base.glob("*/agent_*/transcript.jsonl"))
        except Exception:
            pass
    best = {}  # sess_dir -> (n_msgs, last_len, msgs, path)
    for f in files:
        sess_dir = f.parent.parent.name
        got = _zcode_extract(f)
        if not got:
            continue
        msgs, last_len = got
        if not msgs:
            continue
        cur = best.get(sess_dir)
        key = (len(msgs), last_len)
        if cur is None or key > (cur[0], cur[1]):
            best[sess_dir] = (len(msgs), last_len, msgs, f)
    for sess_dir, (_n, _l, msgs, f) in best.items():
        title, wsp = taskmap.get(sess_dir, ("", None))
        convs.append(finalize(new_conv("ZCode", sess_dir, title, msgs, "", "", wsp, f)))
    return convs


def _copilot_chat_dbs():
    out = []
    for base in (APPDATA, LOCALAPPDATA):
        try:
            for d in base.iterdir():
                if d.is_dir():
                    p = d / "User" / "globalStorage" / "github.copilot-chat" / "session-store.db"
                    if p.is_file():
                        out.append(p)
        except Exception:
            pass
    return out


def scan_copilot_chat():
    """VS Code Copilot Chat: globalStorage/github.copilot-chat/session-store.db."""
    convs = []
    for db in _copilot_chat_dbs():
        con = _open_sqlite_with_wal(db)
        if not con:
            continue
        try:
            tables = table_names(con)
            if "sessions" not in tables or "turns" not in tables:
                continue
            sess = {}
            try:
                for row in con.execute(
                        "SELECT id, cwd, repository, summary, created_at, updated_at FROM sessions"):
                    sess[row[0]] = (row[1] or row[2], row[3], row[4], row[5])
            except Exception:
                pass
            by_sid = {}
            try:
                for sid, user_msg, asst in con.execute(
                        "SELECT session_id, user_message, assistant_response FROM turns "
                        "ORDER BY session_id, turn_index"):
                    if user_msg:
                        by_sid.setdefault(sid, []).append(("user", user_msg))
                    if asst:
                        by_sid.setdefault(sid, []).append(("assistant", asst))
            except Exception:
                pass
            for sid, msgs in by_sid.items():
                cwd, summary, created, updated = sess.get(sid, (None, "", "", ""))
                convs.append(finalize(new_conv(
                    "Copilot Chat", sid, summary, msgs,
                    ts_to_str(created), ts_to_str(updated), cwd, db)))
        finally:
            con.close()
    return convs


SOURCES = [
    ("Qoder", scan_qoder, "自动"),
    ("Claude Code", scan_claude_code, "自动"),
    ("Codex CLI", scan_codex, "自动"),
    ("Gemini CLI", scan_gemini, "自动"),
    ("Kimi Code", scan_kimi, "自动(尽力)"),
    ("Copilot CLI", scan_copilot, "自动(尽力)"),
    ("Cursor", scan_cursor, "自动"),
    ("Windsurf", scan_windsurf, "自动"),
    ("MiMo 小米", scan_mimo, "自动"),
    ("Marvis 腾讯", scan_marvis, "自动"),
    ("LM Studio", scan_lmstudio, "自动"),
    ("OpenClaw", scan_openclaw, "自动"),
    ("ZCode", scan_zcode, "自动"),
    ("Copilot Chat", scan_copilot_chat, "自动(需 WAL)"),
    ("豆包 Doubao", scan_doubao, "自动(尽力)"),
    ("Chatbox", scan_chatbox, "自动"),
    ("ChatGPT/Claude 导出", scan_official_exports, "需官方导出文件"),
]

# Trae / Perplexity / 文心一言 / 通义千问 无法读取（加密库或无本地数据），
# 因此这里不会有对应适配器。


# --------------------------------------------------------------------------
# matching
# --------------------------------------------------------------------------
def match_score(conv, raw_project, toks):
    reasons = []
    score = 0
    np = norm(conv.get("project"))
    rp = norm(raw_project)
    if np and rp and np == rp:
        score += 100
        reasons.append("路径精确匹配")
    elif np and rp and enc_path(conv.get("project")) == enc_path(raw_project):
        score += 90
        reasons.append("项目目录匹配")
    elif np:
        hit = [t for t in toks if t in np]
        if hit:
            score += 60
            reasons.append("路径含关键词:" + ",".join(hit))

    hay_title = (conv.get("title") or "").lower()
    hay_body = "\n".join(m["text"] for m in conv.get("messages", [])).lower()
    title_hits = [t for t in toks if t in hay_title]
    body_hits = [t for t in toks if t in hay_body]
    if title_hits:
        score += 10 * len(title_hits)
        reasons.append("标题含关键词:" + ",".join(title_hits))
    if body_hits:
        score += 4 * len(body_hits)
        reasons.append("内容含关键词:" + ",".join(body_hits))
    return score, reasons


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------
def cmd_sources(args):
    print("已支持的来源:")
    for name, fn, kind in SOURCES:
        print("  - %-22s [%s]" % (name, kind))
    print("\n不支持: Trae(SQLCipher 加密)、Perplexity / 文心一言 / 通义千问(无本地数据)")
    return 0


def cmd_scan(args):
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    toks = tokens_of(args.project)

    only = None
    if args.source:
        only = [s.strip().lower() for s in args.source.split(",")]

    report = []
    all_matches = []
    for name, fn, kind in SOURCES:
        if only and not any(o in name.lower() for o in only):
            continue
        status = {"source": name, "kind": kind, "found": False, "total": 0, "matched": 0, "error": ""}
        try:
            convs = fn()
            status["found"] = len(convs) > 0
            status["total"] = len(convs)
            for c in convs:
                sc, reasons = match_score(c, args.project, toks)
                if sc > 0 or args.all:
                    c["_score"] = sc
                    c["_reason"] = "; ".join(reasons) if reasons else ("全量列出" if args.all else "")
                    all_matches.append(c)
                    status["matched"] += 1
        except Exception as e:
            status["error"] = "%s: %s" % (type(e).__name__, e)
        report.append(status)

    all_matches.sort(key=lambda c: (-c.get("_score", 0), c.get("updated") or "", c.get("created") or ""), reverse=False)
    all_matches.sort(key=lambda c: (-c.get("_score", 0), -(len(c.get("messages", [])))))

    for i, c in enumerate(all_matches, 1):
        c["index"] = i

    scan_file = out_dir / "_scan.json"
    payload = {
        "project": args.project,
        "tokens": toks,
        "created_at": time.strftime("%Y-%m-%d %H:%M"),
        "sources": report,
        "conversations": all_matches,
    }
    scan_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print("目标项目关键词: %s" % args.project)
    print("匹配关键词: %s" % ", ".join(toks))
    print("=" * 64)
    print("本地来源探测结果:")
    for s in report:
        if s["error"]:
            mark = "⚠️"
            extra = "错误: %s" % s["error"]
        elif not s["found"]:
            mark = "❌"
            extra = "未安装 / 无可读数据"
        else:
            mark = "✅"
            extra = "共 %d 个会话，匹配 %d 个" % (s["total"], s["matched"])
        print("  %s %-22s %s" % (mark, s["source"], extra))
    print("-" * 64)
    if not all_matches:
        print("没有找到相关会话。可尝试:")
        print("  · 换一个更贴近项目名/仓库名的关键词")
        print("  · 加 --all 列出全部会话(不筛选)")
        print("  · 对 ChatGPT / Claude，先把官方导出文件放到 Downloads")
    else:
        print("共找到 %d 个相关会话:" % len(all_matches))
        for c in all_matches:
            print("  [%2d] %-12s | %-9s | %2d 条 | %s | %s" % (
                c["index"], c["source"], (c.get("updated") or c.get("created") or "")[:10],
                len(c["messages"]), c["title"][:34], c.get("_reason", "")))
    print("-" * 64)
    print("扫描结果已写入: %s" % scan_file)
    print("下一步: python trae_migrate.py export --out-dir \"%s\" --pick 1,2,3" % out_dir)
    return 0


def _safe_name(s, fallback="conv"):
    s = re.sub(r'[\\/:*?"<>|\r\n\t]+', "-", str(s)).strip(" -.、")
    s = re.sub(r"\s+", " ", s)
    s = s[:50].strip()
    return s or fallback


def cmd_export(args):
    out_dir = Path(args.out_dir).expanduser().resolve()
    scan_file = Path(args.scan).expanduser().resolve() if args.scan else (out_dir / "_scan.json")
    if not scan_file.is_file():
        print("错误: 找不到扫描结果 %s，请先执行 scan" % scan_file, file=sys.stderr)
        return 2
    payload = json.loads(scan_file.read_text(encoding="utf-8"))
    convs = payload.get("conversations", [])

    picks = []
    if args.pick:
        for part in re.split(r"[,\s]+", args.pick.strip()):
            if not part:
                continue
            if "-" in part:
                a, b = part.split("-", 1)
                if a.isdigit() and b.isdigit():
                    picks += list(range(int(a), int(b) + 1))
            elif part.isdigit():
                picks.append(int(part))
    by_index = {c["index"]: c for c in convs}
    chosen = [by_index[i] for i in picks if i in by_index]
    if not chosen:
        print("错误: --pick 未选中任何会话。可选序号: %s" % ", ".join(str(c["index"]) for c in convs), file=sys.stderr)
        return 2

    exp_dir = out_dir / "_migrate_export"
    exp_dir.mkdir(parents=True, exist_ok=True)

    manifest_file = out_dir / "_manifest.json"
    manifest = {}
    if manifest_file.is_file():
        try:
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}

    entries = []
    for n, c in enumerate(chosen, 1):
        slug = "%02d-%s" % (c["index"], _safe_name(c["title"]))
        md = exp_dir / (slug + ".md")
        lines = []
        lines.append("# %s" % c["title"])
        lines.append("")
        lines.append("> 来源: %s ｜ 会话 ID: %s" % (c["source"], c["id"]))
        meta = []
        if c.get("created"):
            meta.append("创建: %s" % c["created"])
        if c.get("updated"):
            meta.append("最后活动: %s" % c["updated"])
        meta.append("消息数: %d" % len(c["messages"]))
        lines.append("> " + " ｜ ".join(meta))
        if c.get("project"):
            lines.append("> 原始项目: %s" % c["project"])
        lines.append("> 原始文件: %s" % c.get("path", ""))
        if c.get("note"):
            lines.append("> 备注: %s" % c["note"])
        lines.append("")
        lines.append("---")
        lines.append("")
        for m in c["messages"]:
            who = {"user": "用户", "assistant": "助手", "tool": "工具"}.get(m["role"], m["role"])
            lines.append("## %s" % who)
            lines.append("")
            lines.append(m["text"])
            lines.append("")
        md.write_text("\n".join(lines), encoding="utf-8")

        entry = {
            "index": c["index"],
            "title": c["title"],
            "source": c["source"],
            "messages": len(c["messages"]),
            "updated": c.get("updated") or c.get("created"),
            "file": "_migrate_export/%s.md" % slug,
            "source_id": c["id"],
        }
        entries.append(entry)
        manifest[md.name] = entry

    manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # -------- index with seed prompts --------
    idx = []
    idx.append("# 迁移对照表 · 共 %d 个会话" % len(entries))
    idx.append("")
    idx.append("目标项目: `%s`" % payload.get("project", ""))
    idx.append("生成时间: %s" % time.strftime("%Y-%m-%d %H:%M"))
    idx.append("")
    idx.append("| 序号 | 标题 | 来源 | 消息数 | 最后活动 | 历史文件 |")
    idx.append("| --- | --- | --- | --- | --- | --- |")
    for e in entries:
        idx.append("| %d | %s | %s | %d | %s | `%s` |" % (
            e["index"], e["title"].replace("|", "\\|"), e["source"], e["messages"],
            (e["updated"] or "")[:16], e["file"]))
    idx.append("")
    idx.append("---")
    idx.append("")
    idx.append("## 怎么在 Trae 里把每个会话变成可继续的独立会话")
    idx.append("")
    idx.append("Trae 没有程序化新建会话的接口，所以最后一步需要你手动完成（每个会话只花几秒）：")
    idx.append("")
    idx.append("1. 在 Trae 里点「新建会话」。")
    idx.append("2. 把下面任意一个「种子提示词」整段粘贴进去发送。")
    idx.append("3. Trae 读完历史文件后，这条会话就带着完整上下文，之后正常接着聊即可。")
    idx.append("")
    idx.append("> 建议：改会话名时**从列表底部往上改**（改名会把它顶到最前，从下往上改才不会乱）。")
    idx.append("")
    idx.append("---")
    idx.append("")
    for e in entries:
        abs_path = (exp_dir / Path(e["file"]).name).resolve()
        idx.append("### [%d] %s" % (e["index"], e["title"]))
        idx.append("")
        idx.append("- 来源: %s ｜ 消息数: %d ｜ 最后活动: %s" % (e["source"], e["messages"], (e["updated"] or "")[:16]))
        idx.append("- 历史文件: `%s`" % abs_path.as_posix())
        idx.append("")
        idx.append("种子提示词（新建 Trae 会话后粘贴）:")
        idx.append("")
        idx.append("```text")
        idx.append("这是我之前在 %s 里的对话历史，请先读取文件 %s 作为上下文，" % (e["source"], abs_path.as_posix()))
        idx.append("读完后基于该历史继续和我讨论。接下来我想说：")
        idx.append("```")
        idx.append("")

    index_file = exp_dir / "_index.md"
    index_file.write_text("\n".join(idx), encoding="utf-8")

    print("已导出 %d 个会话:" % len(entries))
    for e in entries:
        print("  [%2d] %-12s %2d 条  ->  %s" % (e["index"], e["source"], e["messages"], e["file"]))
    print("-" * 64)
    print("对照表(含种子提示词): %s" % index_file)
    print("清单: %s" % manifest_file)
    print("")
    print("接下来: 在 Trae 新建会话 -> 打开 _index.md 复制对应种子提示词粘贴发送。")
    return 0


def build_parser():
    p = argparse.ArgumentParser(description="把本地 AI 工具的历史对话导出到 Trae")
    sub = p.add_subparsers(dest="cmd")

    ps = sub.add_parser("scan", help="扫描本地 AI 工具并筛选相关会话")
    ps.add_argument("--project", required=True, help="项目名 / 仓库名 / 本地路径 / GitHub URL")
    ps.add_argument("--out-dir", default=".trae-import", help="输出目录(默认 .trae-import)")
    ps.add_argument("--source", default="", help="只看某些来源，逗号分隔，如 Cursor,Claude")
    ps.add_argument("--all", action="store_true", help="不筛选，列出全部会话")
    ps.add_argument("--json", action="store_true", help="以 JSON 输出")
    ps.set_defaults(func=cmd_scan)

    pe = sub.add_parser("export", help="导出选中的会话为 Markdown + 种子提示词")
    pe.add_argument("--out-dir", default=".trae-import", help="输出目录(默认 .trae-import)")
    pe.add_argument("--scan", default="", help="扫描结果 json 路径(默认 <out-dir>/_scan.json)")
    pe.add_argument("--pick", default="all", help="要导出的序号，如 1,2,5 或 1-4 或 all")
    pe.set_defaults(func=cmd_export)

    pl = sub.add_parser("sources", help="列出支持的来源")
    pl.set_defaults(func=cmd_sources)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "cmd", None):
        parser.print_help()
        return 1
    if args.cmd == "export" and args.pick == "all":
        out_dir = Path(args.out_dir).expanduser().resolve()
        scan_file = Path(args.scan).expanduser().resolve() if args.scan else (out_dir / "_scan.json")
        if scan_file.is_file():
            payload = json.loads(scan_file.read_text(encoding="utf-8"))
            args.pick = ",".join(str(c["index"]) for c in payload.get("conversations", []))
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())