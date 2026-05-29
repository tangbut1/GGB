from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List


class EventStore:
    """SQLite-backed storage for analyzed market events."""

    def __init__(self, db_path: str | Path = "data/knowledge/events.sqlite3") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    keyword TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT,
                    sentiment_label TEXT,
                    sentiment_score REAL,
                    publish_time TEXT,
                    source_refs TEXT NOT NULL,
                    content_hash TEXT,
                    platform TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                )
                """
            )
            # migration: add platform column to existing tables
            try:
                conn.execute("ALTER TABLE events ADD COLUMN platform TEXT DEFAULT ''")
            except sqlite3.OperationalError:
                pass  # column already exists
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_keyword ON events(keyword)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_task_id ON events(task_id)")

    def save_task_events(
        self,
        task_id: str,
        keyword: str,
        analyzed_news: Iterable[Dict[str, Any]],
    ) -> int:
        rows = []
        created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat() + "Z"
        for news in analyzed_news:
            if not isinstance(news, dict):
                continue
            title = str(news.get("title") or news.get("original_title") or "").strip()
            if not title:
                continue
            platform = news.get("source") or news.get("platform") or ""
            rows.append(
                (
                    task_id,
                    keyword,
                    title,
                    news.get("summary") or news.get("content") or "",
                    news.get("sentiment_label") or "",
                    float(news.get("sentiment_score") or 0.0),
                    news.get("publish_time") or news.get("date") or "",
                    json.dumps(news.get("source_refs") or [], ensure_ascii=False),
                    news.get("content_hash") or "",
                    platform,
                    created_at,
                )
            )

        with self._connect() as conn:
            conn.execute("DELETE FROM events WHERE task_id = ?", (task_id,))
            conn.executemany(
                """
                INSERT INTO events (
                    task_id, keyword, title, summary, sentiment_label,
                    sentiment_score, publish_time, source_refs, content_hash, platform, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return len(rows)

    def find_recent_by_keyword(self, keyword: str, limit: int = 20) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM events
                WHERE keyword = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (keyword, limit),
            ).fetchall()

        result: List[Dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                item["source_refs"] = json.loads(item.get("source_refs") or "[]")
            except json.JSONDecodeError:
                item["source_refs"] = []
            result.append(item)
        return result

    def search_events(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        term = f"%{query.strip()}%"
        if not query.strip():
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM events
                WHERE keyword LIKE ? OR title LIKE ? OR summary LIKE ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (term, term, term, limit),
            ).fetchall()

        result: List[Dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                item["source_refs"] = json.loads(item.get("source_refs") or "[]")
            except json.JSONDecodeError:
                item["source_refs"] = []
            result.append(item)
        return result
