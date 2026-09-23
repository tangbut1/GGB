"""跨会话项目记忆测试。

这一层是"点左侧历史记录看到的是那一次分析"的地基：会话原文、项目记忆、
以及按项目检索。锁住四条：
1. 记忆带来源（哪个会话/任务）与状态（已确认/待验证），可软删除；
2. 检索先按 user/project 收窄，再按关键词命中；
3. 中文按二元切词，"华为"能命中"华为鸿蒙系统"；
4. 所有 SQL 都用参数绑定——外部输入拼进语句一律不接受。
"""

import time

import pytest

from src.knowledge.project_memory import ProjectMemoryStore, build_memory_context


@pytest.fixture
def store(tmp_path):
    s = ProjectMemoryStore(str(tmp_path / "memory.db"))
    yield s
    s.close()


def test_project_is_idempotent_by_name(store):
    a = store.ensure_project("华为")
    b = store.ensure_project("华为")
    assert a == b
    assert len(store.list_projects()) == 1


def test_conversation_lifecycle(store):
    pid = store.ensure_project("华为")
    cid = store.start_conversation(pid, "task_1", "华为")
    store.append_message(cid, "user", "华为最近怎么样", author="user")
    store.append_message(cid, "agent", "红方立论", author="SentimentAgent", round_no=1)
    store.finish_conversation(cid, summary="看空，样本 120 条", status="completed")

    convs = store.list_conversations(pid)
    assert len(convs) == 1
    assert convs[0]["status"] == "completed"
    assert convs[0]["summary"] == "看空，样本 120 条"

    msgs = store.get_messages(cid)
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["round_no"] == 1


def test_find_conversation_by_task(store):
    pid = store.ensure_project("小米")
    cid = store.start_conversation(pid, "task_xyz", "小米")
    assert store.find_conversation_by_task("task_xyz")["conversation_id"] == cid
    assert store.find_conversation_by_task("nope") is None


def test_memory_dedupes_identical_content(store):
    pid = store.ensure_project("比亚迪")
    m1 = store.remember(pid, "Q3 交付量同比下滑", kind="finding", status="confirmed")
    m2 = store.remember(pid, "Q3 交付量同比下滑", kind="finding", status="confirmed")
    assert m1 == m2
    assert len(store.list_memories(pid)) == 1


def test_memory_records_source_and_status(store):
    pid = store.ensure_project("比亚迪")
    cid = store.start_conversation(pid, "task_9", "比亚迪")
    mid = store.remember(
        pid, "价格战压缩毛利", kind="risk", status="pending",
        source_conv=cid, source_task="task_9",
    )
    m = [x for x in store.list_memories(pid) if x["memory_id"] == mid][0]
    assert m["source_conv"] == cid
    assert m["source_task"] == "task_9"
    assert m["status"] == "pending"


def test_retire_memory_is_soft_delete(store):
    pid = store.ensure_project("宁德时代")
    mid = store.remember(pid, "产能扩张过快", kind="risk")
    store.retire_memory(mid)
    # 软删除：默认列表里看不到，但记录还在（来源可追溯）
    assert all(x["memory_id"] != mid for x in store.list_memories(pid))
    assert store.retire_memory(mid) is False  # 已停用，再删一次无事发生


def test_recall_filters_by_project(store):
    p1 = store.ensure_project("华为")
    p2 = store.ensure_project("小米")
    store.remember(p1, "鸿蒙装机量突破", kind="finding")
    store.remember(p2, "汽车业务毛利转正", kind="finding")

    out = store.recall(p1, "鸿蒙")
    assert len(out["memories"]) == 1
    assert "鸿蒙" in out["memories"][0]["content"]
    # 别的项目的记忆不该被带进来
    assert all("小米" not in m["content"] for m in out["memories"])


def test_recall_uses_chinese_bigrams(store):
    pid = store.ensure_project("华为")
    store.remember(pid, "华为鸿蒙系统next版本发布", kind="finding")
    store.remember(pid, "新能源车价格战加剧", kind="finding")

    # "鸿蒙"是两个字的词，必须能命中含它的长句
    out = store.recall(pid, "鸿蒙")
    assert any("鸿蒙" in m["content"] for m in out["memories"])
    # 完全不相关的查询走的是"最近几条"兜底，matched 必须如实说是兜底，
    # 不能伪装成检索命中
    out2 = store.recall(pid, "量子计算")
    assert out2["matched"] is False
    assert len(out2["memories"]) == 2  # 兜底仍给项目内最近的记忆
    # 命中时 matched 为 True
    assert store.recall(pid, "鸿蒙")["matched"] is True


def test_recall_returns_recent_conversations(store):
    pid = store.ensure_project("华为")
    for i in range(3):
        cid = store.start_conversation(pid, f"task_{i}", f"华为 第{i}次")
        store.finish_conversation(cid, summary=f"第{i}次结论")
    out = store.recall(pid, "不匹配任何东西")
    assert len(out["conversations"]) == 3
    # 最近的在最前
    assert out["conversations"][0]["summary"] == "第2次结论"


def test_recall_limits_results(store):
    pid = store.ensure_project("华为")
    for i in range(10):
        store.remember(pid, f"结论{i} 华为", kind="finding")
    out = store.recall(pid, "华为", memory_limit=3, conversation_limit=2)
    assert len(out["memories"]) == 3
    assert len(out["conversations"]) <= 2


def test_build_memory_context_truncates_and_cites_source():
    recall = {
        "memories": [{
            "content": "x" * 5000,
            "status": "confirmed",
            "source_task": "task_1",
            "kind": "risk",
        }],
        "conversations": [{"keyword": "华为", "summary": "y" * 5000, "task_id": "t"}],
    }
    ctx = build_memory_context(recall, max_chars=1200)
    assert len(ctx) <= 1400  # 允许收尾标签的少量超出
    assert "task_1" in ctx  # 来源必须可追溯


def test_build_memory_context_marks_pending_status():
    recall = {
        "memories": [{"content": "待验证结论", "status": "pending", "source_task": "t1", "kind": "finding"}],
        "conversations": [],
    }
    ctx = build_memory_context(recall)
    assert "待验证" in ctx


def test_build_memory_context_empty_when_no_memory():
    assert build_memory_context({"memories": [], "conversations": []}) == ""


def test_stats_counts_all_tables(store):
    pid = store.ensure_project("华为")
    cid = store.start_conversation(pid, "task_1", "华为")
    store.append_message(cid, "agent", "发言", author="SentimentAgent")
    store.remember(pid, "结论", kind="finding")
    stats = store.stats()
    assert stats == {"projects": 1, "conversations": 1, "messages": 1, "project_memories": 1}


def test_sql_injection_attempt_is_treated_as_literal_text(store):
    """外部输入只应是数据：语句不被改写、表还在、内容原样往返。"""
    pid = store.ensure_project("华为")
    payload = "'; DROP TABLE project_memories; --"
    store.remember(pid, payload, kind="finding")
    # 表还在，且这条内容只是被当成普通字符串
    assert store.stats()["project_memories"] == 1
    assert store.list_memories(pid)[0]["content"] == payload
    # 用真正不相关的词查，不应命中
    assert store.recall(pid, "量子计算")["matched"] is False


def test_unknown_task_id_in_message_is_rejected(store):
    pid = store.ensure_project("华为")
    with pytest.raises(Exception):
        store.append_message("no_such_conversation", "agent", "x", author="A")


def test_messages_survive_reopen(tmp_path):
    path = str(tmp_path / "memory.db")
    s1 = ProjectMemoryStore(path)
    pid = s1.ensure_project("华为")
    cid = s1.start_conversation(pid, "task_1", "华为")
    s1.append_message(cid, "agent", "重启前写下的发言", author="SentimentAgent")
    s1.close()

    s2 = ProjectMemoryStore(path)
    convs = s2.list_conversations(pid)
    assert len(convs) == 1
    assert s2.get_messages(cid)[0]["content"] == "重启前写下的发言"
    s2.close()
