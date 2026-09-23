"""TaskStore persistence tests for the Flask layer.

Locks the behaviors that keep "分析记录" honest across restarts:
- a completed/failed task is written to disk while it runs,
- the sidebar list is restored from disk on startup,
- a task still marked ``running`` when the process died is reconciled to
  ``error`` instead of hanging in "分析中" forever,
- ``/history/<task_id>`` falls back to disk for tasks outside the 50-item
  in-memory window.

Uses a stubbed orchestrator, so no network access is required.
"""

import time

import pytest


@pytest.fixture(scope="module")
def flask_app():
    import app as flask_app
    return flask_app


@pytest.fixture
def store(flask_app, tmp_path):
    """Point the app at a throwaway store and isolate task_history."""
    from src.knowledge.task_store import TaskStore
    replacement = TaskStore(str(tmp_path / "tasks"))
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(flask_app, "task_store", replacement)
        mp.setattr(flask_app, "task_history", [])
        yield replacement


def test_store_time_formats_for_sidebar(flask_app):
    """侧边栏取 split(' ')[1] 当时钟，ISO 原样过去会整串渲染。"""
    fmt = flask_app._store_time
    assert fmt({"updated_at": "2026-09-22T20:23:58.123456+08:00"}) == "2026-09-22 20:23:58"
    assert fmt({"updated_at": "2026-09-22T20:23:58"}) == "2026-09-22 20:23:58"
    assert fmt({}) == ""
    assert fmt({"created_at": "2026-09-22T09:00:00+00:00"}) == "2026-09-22 09:00:00"


def test_seed_history_restores_newest_last(flask_app, store):
    """恢复顺序必须和内存追加顺序一致：旧在前、新在后（前端再 reverse）。"""
    store.create("task_old", "旧任务")
    time.sleep(0.01)
    store.create("task_new", "新任务")
    store.update_status("task_old", "completed")
    store.update_status("task_new", "completed")

    flask_app._seed_history_from_store()

    ids = [t["task_id"] for t in flask_app.task_history]
    assert ids == ["task_old", "task_new"]
    for t in flask_app.task_history:
        assert t["status"] == "completed"
        assert t["keyword"]
        assert len(t["time"]) == 19 and t["time"][10] == " "


def test_seed_history_reconciles_stale_running(flask_app, store):
    """进程被杀时还写着 running 的任务永远不会再写终态，必须判为中断。"""
    store.create("task_crashed", "崩溃任务")
    store.create("task_fine", "正常任务")
    store.update_status("task_fine", "completed")

    flask_app._seed_history_from_store()

    crashed = store.get("task_crashed")
    assert crashed["status"] == "error"
    assert "重启" in crashed["error"]

    by_id = {t["task_id"]: t for t in flask_app.task_history}
    assert by_id["task_crashed"]["status"] == "error"
    assert by_id["task_fine"]["status"] == "completed"
    # 恢复后不应再有任何 running 残留
    assert store.list_running() == []


def test_history_detail_falls_back_to_store(flask_app, store):
    """50 条窗口外的老任务：内存里没有，磁盘上还有。"""
    flask_client = flask_app.app.test_client()
    store.create("task_ancient", "很早以前")
    store.update_status("task_ancient", "completed")

    resp = flask_client.get("/history/task_ancient")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["task_id"] == "task_ancient"
    assert body["keyword"] == "很早以前"
    assert body["status"] == "completed"
    assert len(body["time"]) == 19

    # 完全不存在的 id 仍然是 404，不能返回一个空对象让前端当成成功
    assert flask_client.get("/history/task_nope").status_code == 404


def test_completed_task_is_persisted(flask_app, store):
    """跑完的分析必须落盘，否则重启即丢失。"""
    import threading

    release = threading.Event()

    class StubOrchestrator:
        def __init__(self, task_id, keyword, config, forum_manager, monitor,
                     socketio=None, local_data_path=None, src_mode="news",
                     memory_context=""):
            self.task_id = task_id
            self.forum_manager = forum_manager
            self.socketio = socketio

        def run_pipeline(self):
            release.wait(timeout=10)
            self.forum_manager.write("SentimentAgent", 1, "红方立论")
            return {"status": "success", "summary": "done",
                    "data": {"report_data": {"sentiment_summary": {"total_news": 3}}}}

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(flask_app, "OrchestratorAgent", StubOrchestrator)
        resp = flask_app.app.test_client().post(
            "/analyze", json={"keyword": "落盘测试", "srcMode": "news"})
        task_id = resp.get_json()["task_id"]
        release.set()

        deadline = time.time() + 15
        entry = None
        while time.time() < deadline:
            entry = store.get(task_id)
            if entry and entry.get("status") in ("completed", "error"):
                break
            time.sleep(0.2)

    assert entry is not None, "任务没有写入 TaskStore"
    assert entry["status"] == "completed"
    assert entry["keyword"] == "落盘测试"
    assert entry["stats"]["duration_seconds"] >= 0
    assert entry["stats"]["total_news"] == 3


def test_failed_task_is_persisted_with_error(flask_app, store):
    """失败同样要落盘并带上原因，历史里不能只留一个光秃秃的 error。"""
    import threading

    release = threading.Event()

    class FailingOrchestrator:
        def __init__(self, task_id, keyword, config, forum_manager, monitor,
                     socketio=None, local_data_path=None, src_mode="news",
                     memory_context=""):
            self.task_id = task_id
            self.forum_manager = forum_manager

        def run_pipeline(self):
            release.wait(timeout=10)
            return {"status": "error", "message": "采集不到真实结果"}

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(flask_app, "OrchestratorAgent", FailingOrchestrator)
        resp = flask_app.app.test_client().post(
            "/analyze", json={"keyword": "失败测试", "srcMode": "news"})
        task_id = resp.get_json()["task_id"]
        release.set()

        deadline = time.time() + 15
        entry = None
        while time.time() < deadline:
            entry = store.get(task_id)
            if entry and entry.get("status") == "error":
                break
            time.sleep(0.2)

    assert entry["status"] == "error"
    assert entry["error"] == "采集不到真实结果"


# ── 历史对话回放 ──────────────────────────────────────────────────────────
#
# 点左侧历史记录要看的是"那一次"分析：发言原文 + 终裁 + 右侧五个 Tab 的数据。
# 只存 status 字段的话，重新采集拿到的是另一批数据，不是那次分析了。

RESTORABLE_PAYLOAD = {
    "analysis_data": {
        "verdict": {"stance": "negative", "confidence": 0.62, "summary": "风险积聚"},
        "debate_cards": [
            {
                "agent": "SentimentAgent", "agent_label": "红方 · 危机分析师",
                "round": 1, "priority": 1, "full_text": "红方立论：负面占比 40%。",
            },
            {
                "agent": "TrendAgent", "agent_label": "蓝方 · 理性分析师",
                "round": 1, "priority": 2, "full_text": "蓝方立论：情绪噪音被放大。",
            },
            {
                "agent": "HOST", "agent_label": "裁判", "round": 2, "priority": 9,
                "full_text": "终裁：维持警惕。",
            },
        ],
        "sentiment_summary": {"total_news": 12, "negative_count": 5},
    }
}


def test_history_detail_replays_saved_payload(flask_app, store):
    """落盘过的任务必须能原样恢复，restorable=True。"""
    store.create("task_restore_1", keyword="华为")
    store.save_payload("task_restore_1", RESTORABLE_PAYLOAD)

    resp = flask_app.app.test_client().get("/history/task_restore_1")
    assert resp.status_code == 200
    body = resp.get_json()

    assert body["restorable"] is True
    assert body["analysis_data"]["verdict"]["stance"] == "negative"
    assert len(body["turns"]) == 3
    # 顺序按 (round, priority) 还原，和当场看到的一致
    assert [t["author"] for t in body["turns"]] == [
        "SentimentAgent", "TrendAgent", "HOST",
    ]
    assert [t["role"] for t in body["turns"]] == ["red", "blue", "judge"]


def test_history_detail_attaches_verdict_to_judge_turn(flask_app, store):
    """结构化终裁要挂在最后一条裁判发言上，和实时推送时同一形状。"""
    store.create("task_restore_2", keyword="华为")
    store.save_payload("task_restore_2", RESTORABLE_PAYLOAD)

    body = flask_app.app.test_client().get("/history/task_restore_2").get_json()
    judge = [t for t in body["turns"] if t["role"] == "judge"]
    assert len(judge) == 1
    assert judge[0]["kind"] == "verdict"
    assert judge[0]["verdict"]["confidence"] == 0.62


def test_history_detail_without_payload_is_not_restorable(flask_app, store):
    """老任务只落了 status：必须明确说不能回放，不能返回空 turns 冒充成功。"""
    store.create("task_legacy", keyword="旧任务")

    body = flask_app.app.test_client().get("/history/task_legacy").get_json()
    assert body["restorable"] is False
    assert body["turns"] == []
    assert body["analysis_data"] is None


def test_history_detail_unknown_task_is_404(flask_app, store):
    resp = flask_app.app.test_client().get("/history/task_does_not_exist")
    assert resp.status_code == 404


def test_history_detail_falls_back_to_disk(flask_app, store):
    """落在 50 条内存窗口外的老任务，磁盘上还要能取到。"""
    store.create("task_outside_window", keyword="窗口外")
    store.save_payload("task_outside_window", RESTORABLE_PAYLOAD)

    body = flask_app.app.test_client().get("/history/task_outside_window").get_json()
    assert body["restorable"] is True
    assert len(body["turns"]) == 3


def test_history_detail_survives_restart(flask_app, store):
    """"服务重启后还能回放"是这一层的全部意义。"""
    from src.knowledge.task_store import TaskStore

    store.create("task_reopen", keyword="小米")
    store.save_payload("task_reopen", RESTORABLE_PAYLOAD)

    # 换一个 TaskStore 实例指向同一个目录 = 重启后的进程
    reopened = TaskStore(store.store_dir)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(flask_app, "task_store", reopened)
        body = flask_app.app.test_client().get("/history/task_reopen").get_json()

    assert body["restorable"] is True
    assert body["turns"][0]["content"] == "红方立论：负面占比 40%。"


def test_payload_path_cannot_escape_store_dir(store, tmp_path):
    """task_id 可能来自 URL 路径段，不能让它当文件名穿越目录。"""
    store.create("task_safe", keyword="华为")
    payload_dir = store.store_dir / "payload"
    before = {p for p in tmp_path.rglob("*.json") if payload_dir not in p.parents}

    store.save_payload("../escape_attempt", RESTORABLE_PAYLOAD)

    # 唯一重要的不变量：save_payload 不能在 payload 目录之外留下新文件。
    # 具体文件名是清洗的结果，不在此锁定——断言"目录外没有新增"更贴合
    # 要防的事，也不会因为清洗规则微调就误报。
    after = {p for p in tmp_path.rglob("*.json") if payload_dir not in p.parents}
    assert after == before, f"save_payload 写到了 payload 目录之外：{after - before}"
    # 并且用同一个 id 还能读回来（清洗是双向一致的）
    assert store.load_payload("../escape_attempt") is not None


# ReportAgent 落盘的 agent_label 是给报告用的（"危机分析 (Red Team)"），
# 和前端卡片的角色标题不是一套文案。历史回放时若直接透传，同一场辩论
# 直播时显示"红方 · 危机分析师"、点左侧记录变成"危机分析 (Red Team)"。
REAL_LABEL_PAYLOAD = {
    "analysis_data": {
        "verdict": {"stance": "negative", "confidence": 0.7, "summary": "风险积聚"},
        "debate_cards": [
            {
                "agent": "SentimentAgent", "agent_label": "危机分析 (Red Team)",
                "round": 1, "priority": 1, "full_text": "红方立论：负面占比 40%。",
            },
            {
                "agent": "TrendAgent", "agent_label": "理性分析 (Blue Team)",
                "round": 1, "priority": 2, "full_text": "蓝方立论：情绪噪音被放大。",
            },
            {
                "agent": "CollectAgent", "agent_label": "采集Agent",
                "round": 1, "priority": 3, "full_text": "采集 102 条，覆盖 26 天。",
            },
            {
                "agent": "HOST", "agent_label": "研判法官 (Judge)",
                "round": 2, "priority": 9, "full_text": "终裁：维持警惕。",
            },
        ],
    }
}


def test_history_replay_uses_frontend_role_labels(flask_app, store):
    """回放卡片标题必须和实时观看时逐字一致。

    实时路径（_to_debate_turn）不下发 label，前端用 ROLE_STYLES[role].label
    兜底；回放路径若透传后端 agent_label，两边文案就分叉。
    """
    from src.agents.orchestrator import TURN_LABELS

    store.create("task_labels", keyword="宁德时代")
    store.save_payload("task_labels", REAL_LABEL_PAYLOAD)

    body = flask_app.app.test_client().get("/history/task_labels").get_json()
    turns = body["turns"]
    assert [t["role"] for t in turns] == ["red", "blue", "collect", "judge"]

    for turn in turns:
        expected = TURN_LABELS[turn["role"]]
        assert turn["label"] == expected, (
            f"role={turn['role']} 回放标题 {turn['label']!r} != 实时标题 {expected!r}"
        )
    # 角色标题必须自解释：用户分得清谁是哪一方
    assert "红方" in turns[0]["label"] and "蓝方" in turns[1]["label"]
