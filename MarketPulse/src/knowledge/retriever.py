from __future__ import annotations

from typing import List

from .event_store import EventStore


class EventRetriever:
    """Build compact, cited context from persisted market events."""

    def __init__(self, store: EventStore | None = None) -> None:
        self.store = store or EventStore()

    def build_context(self, keyword: str, limit: int = 8) -> str:
        rows = self.store.find_recent_by_keyword(keyword, limit=limit)
        return self._format_rows(rows)

    def search_payload(self, query: str, limit: int = 20) -> dict:
        events = self.store.search_events(query, limit=limit)
        return {
            "query": query,
            "events": events,
            "context": self._format_rows(events),
        }

    def _format_rows(self, rows: list[dict]) -> str:
        if not rows:
            return ""
        lines: List[str] = ["历史事件上下文："]
        for idx, row in enumerate(rows, start=1):
            refs = row.get("source_refs") or []
            ref_text = ",".join(refs) if refs else "none"
            lines.append(
                "[event:{idx}] {title} | sentiment={sentiment} "
                "score={score:.2f} | time={time} | source_refs={refs} | summary={summary}".format(
                    idx=idx,
                    title=row.get("title", ""),
                    sentiment=row.get("sentiment_label", ""),
                    score=float(row.get("sentiment_score") or 0.0),
                    time=row.get("publish_time", ""),
                    refs=ref_text,
                    summary=(row.get("summary") or "")[:120],
                )
            )
        return "\n".join(lines)
