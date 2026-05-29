import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.knowledge.task_store import TaskStore


def test_task_store_create_and_get():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = TaskStore(tmpdir)
        store.create("task_x", "test-keyword", "news")
        entry = store.get("task_x")
        assert entry is not None
        assert entry["task_id"] == "task_x"
        assert entry["keyword"] == "test-keyword"
        assert entry["status"] == "running"


def test_task_store_update_status():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = TaskStore(tmpdir)
        store.create("task_y", "kw", "social")
        store.update_status("task_y", "completed")
        entry = store.get("task_y")
        assert entry["status"] == "completed"
        assert entry["error"] is None


def test_task_store_update_error():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = TaskStore(tmpdir)
        store.create("task_z", "kw", "news")
        store.update_status("task_z", "error", "something broke")
        entry = store.get("task_z")
        assert entry["status"] == "error"
        assert entry["error"] == "something broke"


def test_task_store_list_recent():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = TaskStore(tmpdir)
        store.create("a", "x", "news")
        store.create("b", "y", "social")
        recent = store.list_recent(5)
        assert len(recent) == 2
        ids = {r["task_id"] for r in recent}
        assert ids == {"a", "b"}


def test_task_store_list_running():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = TaskStore(tmpdir)
        store.create("r1", "x", "news")
        store.create("r2", "y", "social")
        store.update_status("r2", "completed")
        running = store.list_running()
        assert running == ["r1"]


def test_task_store_get_missing_returns_none():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = TaskStore(tmpdir)
        assert store.get("nonexistent") is None
