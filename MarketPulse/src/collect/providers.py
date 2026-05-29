"""Source-aware collection helpers.

This module keeps provider metadata close to collection, so downstream agents can
cite evidence without knowing which search backend produced a record.
"""

from __future__ import annotations

import hashlib
import html
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Tuple
from urllib.parse import urlparse


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat() + "Z"


def normalize_url(record: Dict[str, Any]) -> str:
    return (record.get("url") or record.get("link") or "").strip()


def extract_domain(url: str) -> str:
    if not url:
        return ""
    return urlparse(url).netloc.lower()


def content_hash(record: Dict[str, Any]) -> str:
    url = normalize_url(record)
    title = str(record.get("title") or record.get("original_title") or "")
    summary = str(record.get("summary") or record.get("content") or "")
    basis = url or f"{title}\n{summary}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def source_id_for(record: Dict[str, Any]) -> str:
    return "src_" + content_hash(record)[:16]


def annotate_source_refs(
    records: Iterable[Dict[str, Any]],
    collected_at: str | None = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Add source citation metadata to records and return unique source refs."""
    timestamp = collected_at or _utc_timestamp()
    annotated: List[Dict[str, Any]] = []
    sources_by_id: Dict[str, Dict[str, Any]] = {}

    for raw in records:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        # 净化 HTML 实体：&nbsp; → 空格, &amp; → &, &lt;/&gt; → <>, etc.
        for k in ("title", "summary", "content", "original_title"):
            v = item.get(k)
            if isinstance(v, str) and "&" in v:
                item[k] = html.unescape(v)
        url = normalize_url(item)
        if url:
            item["url"] = url
            item["link"] = url
        domain = extract_domain(url)
        digest = content_hash(item)
        sid = "src_" + digest[:16]
        source_ref = {
            "source_id": sid,
            "title": item.get("title") or item.get("original_title") or "",
            "url": url,
            "domain": domain,
            "source": item.get("source") or item.get("platform") or "未知来源",
            "publish_time": item.get("publish_time") or item.get("published") or item.get("date") or "",
            "collected_at": timestamp,
            "content_hash": digest,
        }
        sources_by_id.setdefault(sid, source_ref)
        item["domain"] = domain
        item["content_hash"] = digest
        item["source_refs"] = [sid]
        item["source_ref"] = source_ref
        item["collected_at"] = timestamp
        annotated.append(item)

    return annotated, list(sources_by_id.values())


class SourceAwareCollector:
    """Facade around the existing custom collector that annotates evidence refs."""

    def __init__(self, collector: Any | None = None) -> None:
        self.collector = collector
        self.sources: List[Dict[str, Any]] = []
        self._source_ids = set()

    def _get_collector(self) -> Any:
        if self.collector is None:
            from .custom_search import CustomSearchCollector

            self.collector = CustomSearchCollector()
        return self.collector

    def run_custom_search(self, keyword: str, max_results: int = 120) -> List[Dict[str, Any]]:
        raw_records = self._get_collector().run_custom_search(keyword, max_results=max_results)
        annotated, sources = annotate_source_refs(raw_records)
        for source in sources:
            sid = source.get("source_id")
            if sid and sid not in self._source_ids:
                self._source_ids.add(sid)
                self.sources.append(source)
        return annotated
