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
        self._lock = threading.Lock()

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

    def _path(self, task_id: str) -> Path:
        safe = task_id.replace("/", "_").replace("..", "_")
        return self.store_dir / f"{safe}.json"

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
        with self._lock:
            path.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")


def _now() -> str:
    return datetime.now().astimezone().isoformat()
