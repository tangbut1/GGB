import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.knowledge.event_store import EventStore


def test_event_store_saves_and_loads_events_with_source_refs():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "events.sqlite3")
        store = EventStore(db_path)

        store.save_task_events(
            task_id="task_1",
            keyword="华为",
            analyzed_news=[
                {
                    "title": "华为发布新产品",
                    "summary": "新品发布带动供应链关注。",
                    "sentiment_label": "positive",
                    "sentiment_score": 0.72,
                    "publish_time": "2026-05-23 09:30",
                    "source_refs": ["src_abc"],
                    "content_hash": "abc123",
                }
            ],
        )

        rows = store.find_recent_by_keyword("华为", limit=5)

        assert len(rows) == 1
        assert rows[0]["task_id"] == "task_1"
        assert rows[0]["keyword"] == "华为"
        assert rows[0]["title"] == "华为发布新产品"
        assert rows[0]["source_refs"] == ["src_abc"]
        assert rows[0]["sentiment_label"] == "positive"


def test_event_store_replaces_task_events_for_same_task_id():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "events.sqlite3")
        store = EventStore(db_path)

        store.save_task_events("task_1", "华为", [{"title": "旧事件"}])
        store.save_task_events("task_1", "华为", [{"title": "新事件"}])

        rows = store.find_recent_by_keyword("华为", limit=5)

        assert [row["title"] for row in rows] == ["新事件"]


def test_event_store_searches_keyword_title_and_summary():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "events.sqlite3")
        store = EventStore(db_path)

        store.save_task_events(
            "task_1",
            "新能源",
            [
                {
                    "title": "华为智能车供应链升温",
                    "summary": "汽车零部件订单增长。",
                    "source_refs": ["src_car"],
                },
                {
                    "title": "无关事件",
                    "summary": "普通市场波动。",
                    "source_refs": ["src_other"],
                },
            ],
        )

        rows = store.search_events("智能车", limit=5)

        assert len(rows) == 1
        assert rows[0]["title"] == "华为智能车供应链升温"
        assert rows[0]["source_refs"] == ["src_car"]


if __name__ == "__main__":
    test_event_store_saves_and_loads_events_with_source_refs()
    test_event_store_replaces_task_events_for_same_task_id()
    test_event_store_searches_keyword_title_and_summary()
