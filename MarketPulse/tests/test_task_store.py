import os
import sys
import tempfile
import threading

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


def test_task_store_update_stats_does_not_deadlock():
    """update_stats 在一次持锁内做读-改-写，_read/_write 也取同一把锁。

    锁必须是可重入的，否则它自己把自己锁死——调用方（Flask 后台线程）
    会一直挂着，任务永远写不上终态。
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        store = TaskStore(tmpdir)
        store.create("t", "kw", "news")
        store.update_status("t", "completed")

        done = threading.Event()

        def writer():
            store.update_stats("t", {"duration_seconds": 1.5, "total_news": 7})
            done.set()

        th = threading.Thread(target=writer, daemon=True)
        th.start()
        assert done.wait(timeout=5), "update_stats 死锁了"
        th.join(timeout=5)

        stats = store.get("t")["stats"]
        assert stats["duration_seconds"] == 1.5
        assert stats["total_news"] == 7


def test_task_store_concurrent_updates_keep_all_keys():
    """多线程同时写同一个任务不能丢 key，也不能互相锁死。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = TaskStore(tmpdir)
        store.create("t", "kw", "news")

        def writer(i):
            for n in range(10):
                store.update_stats("t", {f"k{i}": n})

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(4)]
        for th in threads:
            th.start()
        for th in threads:
            th.join(timeout=10)
        assert not any(th.is_alive() for th in threads)

        stats = store.get("t")["stats"]
        assert sorted(k for k in stats if k.startswith("k")) == ["k0", "k1", "k2", "k3"]
