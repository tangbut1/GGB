"""SocketIO contract tests for the Flask layer.

Locks the event shapes the frontend depends on:
- ``debate_turn``: single source (background log emitter), rich shape
  ``{author, type, role, round, content, timestamp}``; SYSTEM/HOST excluded.
- ``forum_message``: judge guidance / structured verdict.
- ``task_complete``: analysis payload including verdict & keywords.

Uses a stubbed orchestrator, so no network access is required.
"""

import threading
import time

import pytest


@pytest.fixture(scope="module")
def flask_app():
    import app as flask_app
    return flask_app


def test_to_debate_turn_filters_internal_messages(flask_app):
    conv = flask_app._to_debate_turn
    assert conv({"agent": "SYSTEM", "round": 1, "content": "内部日志"}) is None
    assert conv({"agent": "HOST", "round": 1, "content": "裁判发言"}) is None
    assert conv({"agent": "SentimentAgent", "round": 1, "content": ""}) is None

    turn = conv({"agent": "SentimentAgent", "round": 2, "content": "红方反驳", "timestamp": "t"})
    assert turn == {
        "author": "SentimentAgent", "type": "AGENT", "role": "red",
        "round": 2, "content": "红方反驳", "timestamp": "t",
    }
    assert conv({"agent": "TrendAgent", "round": 1, "content": "蓝方立论"})["role"] == "blue"


def test_socket_end_to_end_debate_events(flask_app, isolated_memory):
    """A stubbed pipeline must produce exactly the frontend's event contract."""
    socketio = flask_app.socketio
    release = threading.Event()

    class StubOrchestrator:
        def __init__(self, task_id, keyword, config, forum_manager, monitor,
                     socketio=None, local_data_path=None, src_mode="news",
                     memory_context=""):
            self.task_id = task_id
            self.forum_manager = forum_manager
            self.socketio = socketio

        def run_pipeline(self):
            # 等测试端 join 房间后再发言，消除“发言早于 join 丢失”的竞态
            release.wait(timeout=10)

            fm = self.forum_manager
            # 模拟真实辩论：红/蓝各两轮 + 裁判引导与终裁
            fm.write("CollectAgent", 1, "采集到 12 条数据")
            fm.write("SentimentAgent", 1, "红方立论：风险积聚")
            fm.write("TrendAgent", 1, "蓝方立论：基本面稳健")
            fm.write("HOST", 1, "【总结】：分歧在情绪与基本面\n【盲区引导】：@TrendAgent")
            fm.write("SentimentAgent", 2, "红方反驳：@TrendAgent 数据滞后")
            fm.write("TrendAgent", 2, "蓝方反驳：@SentimentAgent 情绪放大")
            fm.write("SYSTEM", 2, "内部消息，不应推送")
            verdict = {"stance": "neutral", "confidence": 0.55, "summary": "势均力敌",
                       "key_disagreements": ["情绪面 vs 基本面"], "action_signal": "neutral"}
            fm.write("HOST", 2, "【终裁】立场：中性")

            self.socketio.emit("forum_message", {
                "agent": "HOST", "role": "judge", "round": 2,
                "content": "【终裁】立场：中性", "kind": "verdict", "verdict": verdict,
            }, room=self.task_id)
            # task_complete 由路由层在 finally 中统一发出，桩不重复发
            return {"status": "success", "summary": "done",
                    "data": {"report_data": {"verdict": verdict, "keywords": ["风险", "基本面"]}}}

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(flask_app, "OrchestratorAgent", StubOrchestrator)

        client = socketio.test_client(flask_app.app)
        assert client.is_connected()

        flask_client = flask_app.app.test_client()
        resp = flask_client.post("/analyze", json={"keyword": "契约测试", "srcMode": "news"})
        assert resp.status_code == 200
        task_id = resp.get_json()["task_id"]

        # 用路由返回的真实 task_id 加入房间，然后放行桩流水线
        client.emit("join", {"task_id": task_id})
        client.get_received()  # 清空 join 回放
        release.set()

        # 等待后台线程完成并让日志广播器把发言刷出来（发言最多晚 1 秒）
        deadline = time.time() + 15
        received = []
        while time.time() < deadline:
            received.extend(client.get_received())
            names = [e["name"] for e in received]
            turns_seen = sum(1 for e in received if e["name"] == "debate_turn")
            if "task_complete" in names and turns_seen >= 5:
                break
            time.sleep(0.3)

        client.disconnect()

    # ── 断言契约 ──
    debate_turns = [e["args"][0] for e in received if e["name"] == "debate_turn"]
    forum_msgs = [e["args"][0] for e in received if e["name"] == "forum_message"]
    completes = [e["args"][0] for e in received if e["name"] == "task_complete"]

    # 发言覆盖红蓝各两轮与采集，且不含内部消息
    authors = {(t["author"], t["round"]) for t in debate_turns}
    assert ("CollectAgent", 1) in authors
    assert ("SentimentAgent", 1) in authors and ("SentimentAgent", 2) in authors
    assert ("TrendAgent", 1) in authors and ("TrendAgent", 2) in authors
    assert all(t["author"] not in ("SYSTEM", "HOST") for t in debate_turns)

    # 富结构字段齐全
    for t in debate_turns:
        assert t["type"] == "AGENT"
        assert t["role"] in ("collect", "red", "blue", "report", "agent")
        assert t["content"]
        assert "timestamp" in t

    # 裁判事件只走 forum_message，且终裁带结构化 verdict
    assert len(forum_msgs) == 1
    assert forum_msgs[0]["kind"] == "verdict"
    assert forum_msgs[0]["verdict"]["stance"] == "neutral"

    # 完成事件带上分析数据
    assert len(completes) == 1
    assert completes[0]["status"] == "completed"
    assert completes[0]["data"]["verdict"]["stance"] == "neutral"
    assert completes[0]["data"]["keywords"] == ["风险", "基本面"]
