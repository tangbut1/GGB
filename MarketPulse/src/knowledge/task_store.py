"""Persist tasks to disk — survive restarts, recover crashed pipelines."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

_DEFAULT_DIR = "data/tasks"


class TaskStore:
    """JSON-file-backed task registry. Each task gets its own .json file."""

    def __init__(self, store_dir: str = _DEFAULT_DIR) -> None:
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        # 可重入锁：update_stats 要在一次持锁内完成"读-改-写"，而 _read /
        # _write 各自也会取同一把锁。用 Lock 会让它自己把自己锁死。
        self._lock = threading.RLock()

    # ── write ────────────────────────────────────────────────────────────────

    def create(self, task_id: str, keyword: str, src_mode: str = "news") -> None:
        entry = {
            "task_id": task_id,
            "keyword": keyword,
            "src_mode": src_mode,
            "status": "running",
            "created_at": _now(),
            "updated_at": _now(),
            "error": None,
        }
        self._write(task_id, entry)

    def update_status(self, task_id: str, status: str, error: str | None = None) -> None:
        entry = self._read(task_id) or {}
        entry["status"] = status
        entry["updated_at"] = _now()
        if error:
            entry["error"] = error
        self._write(task_id, entry)

    def update_stats(self, task_id: str, updates: dict) -> None:
        """Update arbitrary statistics for the task (e.g. durations, counts)."""
        with self._lock:
            entry = self._read(task_id) or {}
            stats = entry.setdefault("stats", {})
            stats.update(updates)
            entry["updated_at"] = _now()
            self._write(task_id, entry)

    # ── payload（完整分析结果） ────────────────────────────────────────────

    def save_payload(self, task_id: str, payload: dict) -> None:
        """把一次分析的完整结果落到 <store_dir>/payload/<task_id>.json。

        任务 JSON 本身只存状态与统计，是为了让 list_recent 能廉价地扫目录。
        完整 analysis_data 有几百 KB（analyzed_news 一家几十条），混在里面
        会让侧边栏每次加载都把整个 results 目录读进内存。

        没有这份文件，点击历史记录就只能重新采集一遍——而重新采集拿到的
        是另一批数据，已经不是"那次分析"了。
        """
        payload_dir = self.store_dir / "payload"
        payload_dir.mkdir(parents=True, exist_ok=True)
        path = payload_dir / f"{self._safe_stem(task_id)}.json"
        tmp = path.with_suffix(".json.tmp")
        with self._lock:
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, path)

    def load_payload(self, task_id: str) -> dict | None:
        path = self.store_dir / "payload" / f"{self._safe_stem(task_id)}.json"
        if not path.exists():
            return None
        try:
            with self._lock:
                return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def has_payload(self, task_id: str) -> bool:
        return (self.store_dir / "payload" / f"{self._safe_stem(task_id)}.json").exists()

    def delete(self, task_id: str) -> bool:
        """删除一条历史记录：任务 JSON + 完整结果 payload。

        两个文件必须一起删。只删任务 JSON 的话 payload 还留在
        payload/ 下，而 _seed_history_from_store 是按任务 JSON 恢复列表的，
        结果是侧边栏看不见它、磁盘上却永远占着几百 KB，且下次同 id 撞名时
        会被旧数据覆盖。

        task_id 仍然走 _safe_stem：URL 路径段是不可信输入，删文件比读文件
        更不该把它直接拼进路径。
        """
        with self._lock:
            removed = False
            for path in (self._path(task_id),
                         self.store_dir / "payload" / f"{self._safe_stem(task_id)}.json"):
                try:
                    path.unlink()
                    removed = True
                except FileNotFoundError:
                    pass
                except OSError:
                    return False
            return removed

    # ── read ─────────────────────────────────────────────────────────────────

    def get(self, task_id: str) -> Dict[str, Any] | None:
        return self._read(task_id)

    def list_recent(self, limit: int = 50) -> list[Dict[str, Any]]:
        files = sorted(self.store_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        tasks: list[Dict[str, Any]] = []
        for f in files[:limit]:
            data = self._read(f.stem)
            if data:
                tasks.append(data)
        return tasks

    def list_running(self) -> list[str]:
        """Return task_ids still marked as 'running' (crashed or in-progress)."""
        running: list[str] = []
        for f in self.store_dir.glob("*.json"):
            data = self._read(f.stem)
            if data and data.get("status") == "running":
                running.append(f.stem)
        return running

    # ── internals ────────────────────────────────────────────────────────────

    def _safe_stem(self, task_id: str) -> str:
        """task_id 可能来自 URL 路径段，先剥掉目录分隔与上级引用再当文件名。"""
        return task_id.replace("/", "_").replace("\\", "_").replace("..", "_")

    def _path(self, task_id: str) -> Path:
        return self.store_dir / f"{self._safe_stem(task_id)}.json"

    def _read(self, task_id: str) -> Dict[str, Any] | None:
        path = self._path(task_id)
        if not path.exists():
            return None
        try:
            with self._lock:
                return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def _write(self, task_id: str, entry: Dict[str, Any]) -> None:
        path = self._path(task_id)
        tmp_path = path.with_suffix(".json.tmp")
        with self._lock:
            tmp_path.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp_path, path)


def _now() -> str:
    return datetime.now().astimezone().isoformat()
