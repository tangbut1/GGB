"""SHA256-based ingest cache — skip re-ingest when source content hasn't changed.

Inspired by llm_wiki's ingest-cache.ts. Prevents redundant search + LLM calls
for the same keyword within a configurable TTL window.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_DEFAULT_DIR = "data/cache"


class IngestCache:
    """Keyed by (keyword, src_mode) → SHA256 of concatenated news content."""

    def __init__(self, cache_dir: str = _DEFAULT_DIR, ttl_seconds: int = 3600) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl_seconds
        self._lock = threading.Lock()

    # ── hash ────────────────────────────────────────────────────────────────

    @staticmethod
    def hash_news(news_list: List[Dict[str, Any]]) -> str:
        titles = sorted(str(n.get("title", "")) for n in news_list if isinstance(n, dict))
        basis = "\n".join(titles)
        return hashlib.sha256(basis.encode("utf-8")).hexdigest()

    # ── cache ops ───────────────────────────────────────────────────────────

    def get(self, keyword: str, src_mode: str) -> Optional[List[Dict[str, Any]]]:
        entry = self._read(keyword, src_mode)
        if not entry:
            return None
        if entry["expires_at"] < time.time():
            self._delete(keyword, src_mode)
            return None
        path = self._data_path(keyword, src_mode)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get("news", [])
        except (json.JSONDecodeError, OSError):
            return None

    def put(self, keyword: str, src_mode: str, news_list: List[Dict[str, Any]]) -> None:
        if not news_list or len(news_list) == 0:
            return  # never cache empty results — poisons entire pipeline
        entry = {
            "keyword": keyword,
            "src_mode": src_mode,
            "hash": self.hash_news(news_list),
            "count": len(news_list),
            "expires_at": time.time() + self.ttl,
            "cached_at": time.time(),
        }
        self._write(keyword, src_mode, entry)
        self._write_data(keyword, src_mode, news_list)

    def has(self, keyword: str, src_mode: str) -> bool:
        entry = self._read(keyword, src_mode)
        if not entry:
            return False
        if entry["expires_at"] < time.time():
            self._delete(keyword, src_mode)
            return False
        return True

    # ── internals ───────────────────────────────────────────────────────────

    def _slug(self, keyword: str, src_mode: str) -> str:
        raw = f"{keyword}_{src_mode}".replace("/", "_").replace(" ", "_")
        return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]

    def _meta_path(self, keyword: str, src_mode: str) -> Path:
        return self.cache_dir / f"{self._slug(keyword, src_mode)}.json"

    def _data_path(self, keyword: str, src_mode: str) -> Path:
        return self.cache_dir / f"{self._slug(keyword, src_mode)}_data.json"

    def _read(self, keyword: str, src_mode: str) -> Optional[Dict[str, Any]]:
        path = self._meta_path(keyword, src_mode)
        if not path.exists():
            return None
        try:
            with self._lock:
                return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def _write(self, keyword: str, src_mode: str, entry: Dict[str, Any]) -> None:
        with self._lock:
            self._meta_path(keyword, src_mode).write_text(
                json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8"
            )

    def _write_data(self, keyword: str, src_mode: str, news_list: List[Dict[str, Any]]) -> None:
        with self._lock:
            self._data_path(keyword, src_mode).write_text(
                json.dumps({"news": news_list}, ensure_ascii=False), encoding="utf-8"
            )

    def _delete(self, keyword: str, src_mode: str) -> None:
        for p in (self._meta_path(keyword, src_mode), self._data_path(keyword, src_mode)):
            try:
                os.remove(p)
            except OSError:
                pass
