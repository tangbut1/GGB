"""清空历史记录必须连项目记忆里的孤儿会话一起清掉。

任务记录（task_store，一个任务一个 JSON）和项目记忆里的会话行是两份数据。
任务 JSON 可以被单独删掉——跑完测试、或者用户早前逐条删过——会话行还留着。
只按 task_id 逐条删就漏下这些孤儿，而 /api/projects 会把它们当成历史对话
返回前端，用户看到的是"我明明清空了，侧栏里还有几十条"。

项目级的 memories 不删：那是跨会话提炼的知识，不是某一次对话的副本。
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.knowledge.project_memory import ProjectMemoryStore
from src.knowledge.task_store import TaskStore


def _seed(store: ProjectMemoryStore):
    """三个项目、三种会话状态：有任务 JSON 的、任务已删的、还有记忆的。"""
    alive = store.ensure_project("存活项目")
    orphan = store.ensure_project("孤儿项目")
    remembered = store.ensure_project("有记忆项目")

    conv = store.start_conversation(alive, "task_alive", "存活")
    store.finish_conversation(conv, "已完成", "ok")
    store.append_message(conv, "SentimentAgent", "红方发言", author="红方")

    # 任务 JSON 已经不在（被单独删过），会话行还挂着
    conv = store.start_conversation(orphan, "task_gone", "已删任务")
    store.finish_conversation(conv, "已完成", "ok")
    store.append_message(conv, "TrendAgent", "蓝方发言", author="蓝方")

    # 有项目级记忆的项目：清会话不该动它
    conv = store.start_conversation(remembered, "task_mem", "有记忆")
    store.finish_conversation(conv, "已完成", "ok")
    store.remember(remembered, "风险口径：负面占比按 T1-T4 分层统计", kind="rule")

    return alive, orphan, remembered


def test_clear_conversations_removes_orphans_and_messages():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ProjectMemoryStore(os.path.join(tmpdir, "mem.db"))
        try:
            _seed(store)
            assert store.stats()["conversations"] == 3
            assert store.stats()["messages"] == 2

            removed = store.clear_conversations()

            assert removed == 3
            stats = store.stats()
            assert stats["conversations"] == 0
            # 发言原文必须跟着走，否则 get_messages 还能取回来，"清空"是假的
            assert stats["messages"] == 0
            # 只剩有项目级记忆的那个。另两个会话清零后什么也不装了，
            # 留着只会让侧栏多出一个点开是"暂无对话"的空标题。
            assert stats["projects"] == 1
            assert stats["project_memories"] == 1
        finally:
            store.close()


def test_clear_conversations_drops_projects_with_no_memories():
    """会话清零后，没有项目级记忆的项目是纯空壳，必须一起删。

    这种壳多半来自一次失败的分析：ensure_project 已经建了行，会话却没写
    进来。它会让 /api/projects 继续把这个项目返回给前端，侧栏"分析记录"
    底下挂着一个空组，用户会以为删除没生效。
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ProjectMemoryStore(os.path.join(tmpdir, "mem.db"))
        try:
            empty = store.ensure_project("空壳项目")
            keep = store.ensure_project("有记忆项目")

            conv = store.start_conversation(empty, "task_empty", "空壳")
            store.finish_conversation(conv, "已完成", "ok")
            store.remember(keep, "口径：负面占比按 T1-T4 分层统计", kind="rule")

            assert store.stats()["projects"] == 2

            store.clear_conversations()

            assert store.stats()["conversations"] == 0
            # 有记忆的留下（记忆是跨会话沉淀的知识，不是某次对话的副本），
            # 空壳消失
            remaining = {p["name"] for p in store.list_projects()}
            assert remaining == {"有记忆项目"}
            assert store.stats()["project_memories"] == 1
        finally:
            store.close()


def test_clear_conversations_keeps_project_with_memories_but_no_conversations():
    """反方向：会话早就没了、只剩记忆的项目，不能因为清空而被删掉。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ProjectMemoryStore(os.path.join(tmpdir, "mem.db"))
        try:
            pid = store.ensure_project("只剩记忆")
            conv = store.start_conversation(pid, "task_old", "老对话")
            store.finish_conversation(conv, "已完成", "ok")
            store.remember(pid, "结论：以 Q3 装机量为验证锚点", kind="finding")

            # 先单独删掉那次会话，模拟"逐条删过"的历史
            store.delete_conversation_by_task("task_old")
            assert store.stats()["conversations"] == 0

            store.clear_conversations()

            names = {p["name"] for p in store.list_projects()}
            assert names == {"只剩记忆"}
            assert store.stats()["project_memories"] == 1
        finally:
            store.close()


def test_clear_conversations_is_idempotent():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ProjectMemoryStore(os.path.join(tmpdir, "mem.db"))
        try:
            _seed(store)
            assert store.clear_conversations() == 3
            assert store.clear_conversations() == 0
        finally:
            store.close()


def test_clear_history_purges_conversations_without_task_json():
    """模拟 history_clear 的真实时序：任务 JSON 逐个删，孤儿会话兜底清。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        task_store = TaskStore(tmpdir)
        store = ProjectMemoryStore(os.path.join(tmpdir, "mem.db"))
        try:
            _seed(store)
            # 只有一个任务的 JSON 还在磁盘上
            task_store.create("task_alive", "存活")

            on_disk = [t.get("task_id") for t in task_store.list_all()]
            for task_id in on_disk:
                task_store.delete(task_id)
                store.delete_conversation_by_task(task_id)
            orphaned = store.clear_conversations()

            assert on_disk == ["task_alive"]
            # 另两条没有任务 JSON，只能靠兜底清掉
            assert orphaned == 2
            assert store.stats()["conversations"] == 0
            assert store.stats()["messages"] == 0
        finally:
            store.close()
