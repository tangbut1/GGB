"""历史记录删除的落盘行为。

删一条历史记录要同时清掉任务 JSON 和完整结果 payload。只删前者的话，
磁盘上会留下几百 KB 永远恢复不出来的残影；_seed_history_from_store 又是
按任务 JSON 恢复列表的，所以侧边栏看不见它、它却一直占着地方。
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.knowledge.task_store import TaskStore


def test_delete_removes_entry_and_payload_together():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = TaskStore(tmpdir)
        store.create("task_del", "kw")
        store.save_payload("task_del", {"analysis_data": {"keyword": "kw"}})
        assert store.has_payload("task_del")

        assert store.delete("task_del") is True
        assert store.get("task_del") is None
        assert store.has_payload("task_del") is False


def test_delete_unknown_id_returns_false():
    with tempfile.TemporaryDirectory() as tmpdir:
        assert TaskStore(tmpdir).delete("nope") is False


def test_delete_clears_orphan_payload():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = TaskStore(tmpdir)
        store.create("task_p", "kw")
        store.save_payload("task_p", {"x": 1})
        # 任务 JSON 已不在时 payload 仍在，delete 仍应报告成功并清掉它
        os.unlink(store.store_dir / "task_p.json")
        assert store.delete("task_p") is True
        assert store.has_payload("task_p") is False


def test_delete_is_idempotent():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = TaskStore(tmpdir)
        store.create("task_i", "kw")
        assert store.delete("task_i") is True
        assert store.delete("task_i") is False
