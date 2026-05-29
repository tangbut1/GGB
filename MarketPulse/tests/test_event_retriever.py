import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.knowledge.event_store import EventStore
from src.knowledge.retriever import EventRetriever


def test_event_retriever_builds_cited_context_from_recent_events():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = EventStore(os.path.join(tmpdir, "events.sqlite3"))
        store.save_task_events(
            task_id="task_1",
            keyword="华为",
            analyzed_news=[
                {
                    "title": "华为供应链订单增长",
                    "summary": "供应链订单增长推动市场预期。",
                    "sentiment_label": "positive",
                    "sentiment_score": 0.7,
                    "source_refs": ["src_a"],
                    "publish_time": "2026-05-23 09:30",
                },
                {
                    "title": "华为交付风险升温",
                    "summary": "短期交付存在扰动。",
                    "sentiment_label": "negative",
                    "sentiment_score": -0.6,
                    "source_refs": ["src_b"],
                    "publish_time": "2026-05-23 10:00",
                },
            ],
        )

        context = EventRetriever(store).build_context("华为", limit=2)

        assert "历史事件上下文" in context
        assert "[event:1]" in context
        assert "华为供应链订单增长" in context
        assert "source_refs=src_a" in context
        assert "sentiment=positive" in context


def test_event_retriever_search_payload_returns_events_and_context():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = EventStore(os.path.join(tmpdir, "events.sqlite3"))
        store.save_task_events(
            task_id="task_1",
            keyword="新能源",
            analyzed_news=[
                {
                    "title": "华为智能车供应链升温",
                    "summary": "汽车零部件订单增长。",
                    "sentiment_label": "positive",
                    "sentiment_score": 0.5,
                    "source_refs": ["src_car"],
                }
            ],
        )

        payload = EventRetriever(store).search_payload("智能车", limit=5)

        assert payload["query"] == "智能车"
        assert len(payload["events"]) == 1
        assert "华为智能车供应链升温" in payload["context"]


if __name__ == "__main__":
    test_event_retriever_builds_cited_context_from_recent_events()
    test_event_retriever_search_payload_returns_events_and_context()
