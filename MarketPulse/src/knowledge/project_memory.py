"""跨会话项目记忆层。

论坛日志（`src/forum/log_manager.py`）只服务**一次分析任务内**的 Agent 交流，
进程重启即丢失。本模块补的是另一件事：不同任务、不同对话之间的连续性。

数据分四层，对应"当前会话 / 项目资料 / 项目长期记忆 / 历史原文"：

    projects          项目（舆情监测主题），跨对话共享
    conversations     一次分析 = 一条会话，归属某个 project
    messages          会话内的发言原文，可回溯
    project_memories  提炼后的结论，带来源与会话 id，可标"已确认/待验证"

设计约束：
  - 所有 SQL 一律参数绑定。本模块的输入（keyword、content）来自用户和 LLM
    输出，拼接 SQL 会把注入面直接开到数据库上。表名同样写死在语句里，
    不用循环拼 f-string——SQL 结构必须是编译期常量。
  - 记忆是**追加**的，不改写历史原文。提炼错误时可以按来源会话查回原话纠正，
    所以 messages 必须原文保留。
  - SQLite 单文件 + WAL：读多写少，且要能被多个后端线程并发访问。
"""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

_DEFAULT_PATH = "data/memory/project_memory.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    project_id   TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    summary      TEXT NOT NULL DEFAULT '',
    created_at   REAL NOT NULL,
    updated_at   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    task_id         TEXT NOT NULL,
    keyword         TEXT NOT NULL,
    title           TEXT NOT NULL DEFAULT '',
    summary         TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'running',
    started_at      REAL NOT NULL,
    ended_at        REAL
);

CREATE TABLE IF NOT EXISTS messages (
    message_id      TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    role            TEXT NOT NULL,
    author          TEXT NOT NULL DEFAULT '',
    round_no        INTEGER NOT NULL DEFAULT 0,
    content         TEXT NOT NULL,
    ts              REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS project_memories (
    memory_id     TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    kind          TEXT NOT NULL DEFAULT 'note',
    content       TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'confirmed',
    source_conv   TEXT,
    source_task   TEXT,
    created_at    REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_conv_project   ON conversations(project_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_msg_conv        ON messages(conversation_id, ts);
CREATE INDEX IF NOT EXISTS idx_mem_project     ON project_memories(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_mem_source_conv ON project_memories(source_conv);
"""

# 停用词：检索时剔掉，否则"的""了"会命中一半行。
_STOPWORDS = {
    "的", "了", "是", "在", "和", "与", "对", "也", "就", "都", "这", "那",
    "有", "被", "把", "从", "向", "为", "以", "及", "等", "个", "之", "其",
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is",
}


def _ngrams(chars: List[str]) -> List[str]:
    if len(chars) == 1:
        return [chars[0]]
    return ["".join(chars[i:i + 2]) for i in range(len(chars) - 1)]


def _tokenize(text: str) -> List[str]:
    """中英混排的关键词切分。

    英文按空白与标点切；中文没有天然分隔，这里对连续汉字段做 2-gram 滑窗，
    配合 LIKE 检索够用。真正的语义检索要等语料量大到关键词找不全时再上
    pgvector，那时候需要换存储，不是改这个函数能解决的。
    """
    if not text:
        return []

    tokens: List[str] = []
    run: List[str] = []          # 连续汉字段
    buf: List[str] = []          # 连续 ASCII 词

    def flush_run() -> None:
        if run:
            tokens.extend(_ngrams(run))
            run.clear()

    def flush_buf() -> None:
        if buf:
            word = "".join(buf).lower()
            if word not in _STOPWORDS:
                tokens.append(word)
            buf.clear()

    for ch in text:
        if ch.isascii() and (ch.isalnum() or ch == "_"):
            flush_run()
            buf.append(ch)
            continue
        flush_buf()
        if "\u4e00" <= ch <= "\u9fff":
            run.append(ch)
    flush_run()
    flush_buf()

    seen: set[str] = set()
    out: List[str] = []
    for t in tokens:
        if t in _STOPWORDS or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


class ProjectMemoryStore:
    """SQLite 支撑的跨会话项目记忆。

    线程安全：连接按线程存放（threading.local），避免 Flask 后台分析线程
    与请求线程共用一个连接时踩 sqlite3 的
    "objects created in a thread can only be used in that same thread"。
    写路径再套一把 RLock 串行化。
    """

    def __init__(self, db_path: str = _DEFAULT_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._local = threading.local()
        self._init_schema()

    # ── 连接 ────────────────────────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self.db_path), timeout=30, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = conn
        return conn

    def _init_schema(self) -> None:
        with self._lock:
            conn = self._conn()
            conn.executescript(_SCHEMA)
            conn.commit()

    @staticmethod
    def _rows(cur: sqlite3.Cursor) -> List[Dict[str, Any]]:
        return [dict(r) for r in cur.fetchall()]

    # ── 项目 ────────────────────────────────────────────────────────────────

    def ensure_project(self, name: str) -> str:
        """按名字取项目，没有则建。

        项目名即主题（"小米汽车"）。同一主题的多次分析归到同一项目下，
        跨对话记忆才有落脚点。名字相同时不新建，避免每跑一次多一个空壳。
        """
        name = (name or "").strip() or "未命名项目"
        with self._lock:
            cur = self._conn().execute(
                "SELECT project_id FROM projects WHERE name = ?", (name,)
            )
            row = cur.fetchone()
            if row:
                return row["project_id"]
            project_id = f"proj_{uuid.uuid4().hex[:12]}"
            now = time.time()
            self._conn().execute(
                "INSERT INTO projects (project_id, name, summary, created_at, updated_at)"
                " VALUES (?, ?, '', ?, ?)",
                (project_id, name, now, now),
            )
            self._conn().commit()
            return project_id

    def update_project_summary(self, project_id: str, summary: str) -> None:
        with self._lock:
            self._conn().execute(
                "UPDATE projects SET summary = ?, updated_at = ? WHERE project_id = ?",
                (summary, time.time(), project_id),
            )
            self._conn().commit()

    def list_projects(self, limit: int = 50) -> List[Dict[str, Any]]:
        """项目列表，附带会话数与最近活动时间。"""
        with self._lock:
            cur = self._conn().execute(
                "SELECT p.project_id, p.name, p.summary, p.created_at, p.updated_at,"
                "       COUNT(DISTINCT c.conversation_id) AS conversation_count,"
                "       COUNT(DISTINCT m.memory_id)        AS memory_count,"
                "       MAX(c.started_at)                  AS last_active"
                "  FROM projects p"
                "  LEFT JOIN conversations     c ON c.project_id = p.project_id"
                "  LEFT JOIN project_memories  m ON m.project_id = p.project_id"
                "                                 AND m.status != 'retired'"
                " GROUP BY p.project_id"
                " ORDER BY last_active DESC, p.updated_at DESC"
                " LIMIT ?",
                (limit,),
            )
            return self._rows(cur)

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            cur = self._conn().execute(
                "SELECT * FROM projects WHERE project_id = ?", (project_id,)
            )
            row = cur.fetchone()
            return dict(row) if row else None

    # ── 会话 ────────────────────────────────────────────────────────────────

    def start_conversation(self, project_id: str, task_id: str, keyword: str) -> str:
        conversation_id = f"conv_{uuid.uuid4().hex[:12]}"
        with self._lock:
            self._conn().execute(
                "INSERT INTO conversations"
                " (conversation_id, project_id, task_id, keyword, title, status, started_at)"
                " VALUES (?, ?, ?, ?, ?, 'running', ?)",
                (conversation_id, project_id, task_id, keyword, keyword, time.time()),
            )
            self._conn().commit()
        return conversation_id

    def finish_conversation(
        self,
        conversation_id: str,
        summary: str = "",
        status: str = "completed",
    ) -> None:
        with self._lock:
            self._conn().execute(
                "UPDATE conversations SET summary = ?, status = ?, ended_at = ?"
                " WHERE conversation_id = ?",
                (summary, status, time.time(), conversation_id),
            )
            self._conn().commit()

    def list_conversations(self, project_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        # started_at 只到秒，连续分析同一主题会撞相同时间戳。补一个 rowid
        # 作次级排序，否则同秒的几条顺序随机，左侧历史列表会在刷新之间跳动。
        with self._lock:
            cur = self._conn().execute(
                "SELECT * FROM conversations WHERE project_id = ?"
                " ORDER BY started_at DESC, rowid DESC LIMIT ?",
                (project_id, limit),
            )
            return self._rows(cur)

    def find_conversation_by_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            cur = self._conn().execute(
                "SELECT * FROM conversations WHERE task_id = ?", (task_id,)
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def all_conversations(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            cur = self._conn().execute(
                "SELECT * FROM conversations ORDER BY started_at DESC LIMIT ?",
                (limit,),
            )
            return self._rows(cur)

    # ── 发言原文 ────────────────────────────────────────────────────────────

    def append_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        author: str = "",
        round_no: int = 0,
    ) -> None:
        if not content:
            return
        with self._lock:
            self._conn().execute(
                "INSERT INTO messages"
                " (message_id, conversation_id, role, author, round_no, content, ts)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    f"msg_{uuid.uuid4().hex[:12]}",
                    conversation_id,
                    role,
                    author,
                    int(round_no or 0),
                    content,
                    time.time(),
                ),
            )
            self._conn().commit()

    def get_messages(self, conversation_id: str, limit: int = 500) -> List[Dict[str, Any]]:
        with self._lock:
            cur = self._conn().execute(
                "SELECT * FROM messages WHERE conversation_id = ?"
                " ORDER BY ts, rowid LIMIT ?",
                (conversation_id, limit),
            )
            return self._rows(cur)

    # ── 长期记忆 ────────────────────────────────────────────────────────────

    def remember(
        self,
        project_id: str,
        content: str,
        kind: str = "note",
        status: str = "confirmed",
        source_conv: Optional[str] = None,
        source_task: Optional[str] = None,
    ) -> str:
        content = (content or "").strip()
        if not content:
            return ""
        # 同项目同内容的记忆不重复入库：追问轮会反复产出同一条结论，
        # 不去重会让"项目记忆"迅速变成同一句话的几十个副本。
        with self._lock:
            cur = self._conn().execute(
                "SELECT memory_id FROM project_memories"
                " WHERE project_id = ? AND content = ? AND status != 'retired'",
                (project_id, content),
            )
            row = cur.fetchone()
            if row:
                return row["memory_id"]
            memory_id = f"mem_{uuid.uuid4().hex[:12]}"
            self._conn().execute(
                "INSERT INTO project_memories"
                " (memory_id, project_id, kind, content, status, source_conv, source_task, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (memory_id, project_id, kind, content, status, source_conv, source_task, time.time()),
            )
            self._conn().commit()
            return memory_id

    def list_memories(
        self,
        project_id: str,
        include_retired: bool = False,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM project_memories WHERE project_id = ?"
        params: List[Any] = [project_id]
        if not include_retired:
            sql += " AND status != 'retired'"
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            return self._rows(self._conn().execute(sql, params))

    def retire_memory(self, memory_id: str) -> bool:
        """软删除：记忆过时或提炼错误时保留记录但不再注入。

        直接 DELETE 会让"这条结论是哪来的"彻底查不到，而记忆最常见的失效
        方式恰恰是结论变了、需要对比新旧两版。

        返回 False 表示"这次调用没有改变任何东西"——id 不存在或早已停用。
        调用方（前端删除按钮）要靠这个区分"删成功了"和"已经删过了"。
        """
        with self._lock:
            cur = self._conn().execute(
                "UPDATE project_memories SET status = 'retired'"
                " WHERE memory_id = ? AND status != 'retired'",
                (memory_id,),
            )
            self._conn().commit()
            return cur.rowcount > 0

    # ── 检索 ────────────────────────────────────────────────────────────────

    def recall(
        self,
        project_id: str,
        query: str,
        memory_limit: int = 6,
        conversation_limit: int = 3,
    ) -> Dict[str, Any]:
        """按 project_id 圈定范围，再按关键词找关联记忆与会话。

        先过滤项目再检索，是防止不同项目内容串台的关键：关键词相同的两个
        主题（都叫"风险预警"）不靠 project_id 分开就会互相污染。
        """
        tokens = _tokenize(query)
        with self._lock:
            memories = self.list_memories(project_id, limit=200)
            conversations = self.list_conversations(project_id, limit=50)

        scored_mem = self._score(memories, tokens, ("content", "kind"))
        scored_conv = self._score(conversations, tokens, ("keyword", "title", "summary"))

        # 没有命中任何 token 时退回最近几条：新主题的首轮分析没有任何历史，
        # 此时给最近上下文比给空列表更有用（用户往往在追同一个事件的后续）。
        # matched=False 明确告诉调用方"这是兜底不是检索命中"，界面上不能
        # 把它说成"检索到 N 条相关记忆"。
        matched_mem = bool(scored_mem)
        matched_conv = bool(scored_conv)
        if not scored_mem:
            scored_mem = [(m, 0.0) for m in memories[:memory_limit]]
        if not scored_conv:
            scored_conv = [(c, 0.0) for c in conversations[:conversation_limit]]

        return {
            "project_id": project_id,
            "query": query,
            "tokens": tokens,
            "matched": matched_mem or matched_conv,
            "memories": [m for m, _ in scored_mem[:memory_limit]],
            "conversations": [c for c, _ in scored_conv[:conversation_limit]],
        }

    @staticmethod
    def _score(
        rows: List[Dict[str, Any]],
        tokens: List[str],
        fields: Iterable[str],
    ) -> List[tuple[Dict[str, Any], float]]:
        if not tokens:
            return []
        scored: List[tuple[Dict[str, Any], float]] = []
        for row in rows:
            haystack = " ".join(str(row.get(f) or "") for f in fields).lower()
            if not haystack:
                continue
            hits = sum(1 for t in tokens if t in haystack)
            if hits == 0:
                continue
            # 归一化到 0~1：命中比例为主、绝对命中数为辅，避免长 query 天然高分
            score = hits / len(tokens) + min(hits, 5) * 0.02
            scored.append((row, round(score, 4)))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def stats(self) -> Dict[str, int]:
        # 表名写死在四条独立语句里，不用循环拼 f-string：SQL 结构必须是
        # 编译期常量，即使表名来自内部元组也不开这个口子。
        with self._lock:
            conn = self._conn()
            return {
                "projects": int(conn.execute(
                    "SELECT COUNT(*) AS n FROM projects").fetchone()["n"]),
                "conversations": int(conn.execute(
                    "SELECT COUNT(*) AS n FROM conversations").fetchone()["n"]),
                "messages": int(conn.execute(
                    "SELECT COUNT(*) AS n FROM messages").fetchone()["n"]),
                "project_memories": int(conn.execute(
                    "SELECT COUNT(*) AS n FROM project_memories").fetchone()["n"]),
            }

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None


def build_memory_context(recall: Dict[str, Any], max_chars: int = 1200) -> str:
    """把检索结果压成一段可注入 prompt 的上下文。

    摘要控制上下文长度：不加截断时一次 recall 能把几千字塞进 prompt，
    既贵又把真正相关的几条淹掉。

    两条硬规则：
    - 没有任何可注入内容时返回空串。orchestrator 用空串判断"这个主题是
      首次分析"，塞一个只有标题的空壳进去会让首次分析也背上历史包袱。
    - 每条都带来源（哪个任务）。没有来源的结论无法复核，模型也没法在
      结论冲突时说明"依据的是哪一次"。
    """
    if not recall:
        return ""
    memories = recall.get("memories") or []
    conversations = recall.get("conversations") or []
    if not memories and not conversations:
        return ""

    lines: List[str] = [
        "[项目记忆] 以下是同一主题下此前的分析结论，可作为背景参考；"
        "若与本次数据矛盾，以本次数据为准："
    ]
    for mem in memories:
        status = "已确认" if mem.get("status") == "confirmed" else "待验证"
        body = str(mem.get("content", "")).strip()
        if not body:
            continue
        source = mem.get("source_task") or mem.get("source_conv")
        cite = f"（来源 {source}）" if source else "（来源未知）"
        lines.append(f"- ({mem.get('kind', 'note')}/{status}) {body[:200]}{cite}")
    for conv in conversations:
        when = time.strftime("%Y-%m-%d", time.localtime(conv.get("started_at") or time.time()))
        summary = (conv.get("summary") or "").strip()
        lines.append(f"- 历史分析 {when}「{conv.get('keyword', '')}」"
                     + (f"：{summary[:160]}" if summary else "（无摘要）"))
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n…（上下文已截断）"
    return text
