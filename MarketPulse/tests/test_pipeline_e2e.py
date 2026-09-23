"""End-to-end pipeline test using mock agents.

Verifies the full red-blue debate orchestrator flow: event generation,
round structure (opening statements → judge guidance → rebuttals →
structured verdict), TaskStore persistence, and report path construction —
without any real network or LLM calls.
"""

import os
import time
import tempfile
import shutil
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helpers — deterministic mock Agent.run() returns
# ---------------------------------------------------------------------------

_MOCK_NEWS = [
    {
        "title": "测试新闻标题",
        "summary": "测试新闻摘要内容",
        "url": "https://example.com/1",
        "publish_time": "2025-01-01 12:00:00",
        "source": "mock_source",
        "category": "测试",
        "sentiment_score": 0.6,
        "sentiment_label": "positive",
        "sentiment_confidence": 0.8,
    }
]

_COLLECT_RESULT = {
    "status": "success",
    "agent": "CollectAgent",
    "data": {
        "news": _MOCK_NEWS,
        "local_records": [],
        "collect_meta": {
            "total_count": 1,
            "source_count": 1,
            "date_range": "2025-01-01",
            "src_mode": "news",
            "sources": [{"name": "mock_source", "count": 1}],
        },
    },
    "summary": "采集了 1 条测试数据",
}

_SENTIMENT_RESULT = {
    "status": "success",
    "agent": "SentimentAgent",
    "data": {
        "analyzed_news": _MOCK_NEWS,
        "summary": {
            "total_news": 1,
            "positive_count": 1,
            "negative_count": 0,
            "neutral_count": 0,
            "avg_sentiment": 0.6,
            "sentiment_distribution": {"positive": 1, "negative": 0, "neutral": 0},
        },
    },
    "summary": "情感分析完成",
}

_TREND_RESULT = {
    "status": "success",
    "agent": "TrendAgent",
    "data": {
        "trend_summary": {
            "trend_direction": "positive",
            "confidence": 0.75,
            "data_quality": "良好",
            "forecast_window": 30,
        },
        "trend_results": {"predictions": []},
    },
    "summary": "趋势预测完成",
}

_REPORT_RESULT = {
    "status": "success",
    "agent": "ReportAgent",
    "data": {
        "report_data": {
            "keyword": "测试",
            "sentiment_summary": _SENTIMENT_RESULT["data"]["summary"],
            "trend_summary": _TREND_RESULT["data"]["trend_summary"],
            "analyzed_news": _MOCK_NEWS,
            "ai_insights": {"headline": "测试洞察"},
            "forum_debate": [],
        }
    },
    "summary": "测试报告生成完成",
}

_MOCK_VERDICT = {
    "stance": "neutral",
    "confidence": 0.6,
    "summary": "测试终裁摘要",
    "key_disagreements": ["分歧点A"],
    "red_strongest": "红方论据",
    "blue_strongest": "蓝方论据",
    "action_signal": "neutral",
    "recommendation": "测试建议",
}


# ---------------------------------------------------------------------------
# Minimal no-op Forum / Monitor stubs
# ---------------------------------------------------------------------------

class _StubLogManager:
    """结构化论坛日志桩：记录 (agent, round, content) 三元组。"""

    def __init__(self, task_id: str):
        self.task_id = task_id
        self._messages: list[dict] = []

    def write(self, agent_name, iteration, content):
        self._messages.append(
            {"agent": agent_name, "round": iteration, "content": content})

    def get_all_messages(self):
        return list(self._messages)

    def read_all_lines(self):
        return [f"[{m['agent']}] {m['content']}" for m in self._messages]

    def get_latest_host_guidance(self):
        return ""

    def set_monitor(self, monitor):
        pass


class _StubMonitor:
    def start(self):
        pass

    def stop(self):
        pass

    def wait_for_host_guidance(self, timeout=10):
        return ""


def _make_orchestrator(task_id: str, keyword: str, forum: _StubLogManager,
                       monitor: _StubMonitor) -> "object":
    from src.agents.orchestrator import OrchestratorAgent

    config = {
        "agent_llm": {
            "collect_agent": {},
            "sentiment_agent": {},
            "trend_agent": {},
            "report_agent": {},
            "forum_host": {},
        }
    }
    return OrchestratorAgent(
        task_id=task_id, keyword=keyword, config=config,
        forum_manager=forum, monitor=monitor, src_mode="news",
    )


def _patch_debate_agents(orch, forum: _StubLogManager):
    """把各 Agent 的 run 换成会向论坛发言的桩，模拟真实辩论。"""
    def fake_sentiment(payload):
        rnd = getattr(orch.sentiment_agent, "iteration_count", 1)
        text = (f"红方第{rnd}轮发言"
                + (f"，驳斥：{payload['feedback'][:40]}" if payload.get("feedback") else "，立论"))
        forum.write("SentimentAgent", rnd, text)
        return _SENTIMENT_RESULT

    def fake_trend(payload):
        rnd = getattr(orch.trend_agent, "iteration_count", 1)
        text = (f"蓝方第{rnd}轮发言"
                + (f"，驳斥：{payload['feedback'][:40]}" if payload.get("feedback") else "，立论"))
        forum.write("TrendAgent", rnd, text)
        return _TREND_RESULT

    orch.collect_agent.run = MagicMock(return_value=_COLLECT_RESULT)
    orch.sentiment_agent.run = MagicMock(side_effect=fake_sentiment)
    orch.trend_agent.run = MagicMock(side_effect=fake_trend)

    def fake_report(payload):
        result = dict(_REPORT_RESULT)
        result["data"] = {
            "report_data": dict(_REPORT_RESULT["data"]["report_data"],
                               keyword=payload.get("keyword", "测试"))
        }
        return result

    orch.report_agent.run = MagicMock(side_effect=fake_report)
    # 裁判 LLM 不可用时的引导由桩提供；终裁走真实降级路径（无网络）
    orch.host.generate_guidance = MagicMock(return_value="【总结】：核心分歧在情绪与基本面\n【盲区引导】：@TrendAgent 请用数据回应")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_pipeline_e2e_produces_report_event():
    """Full pipeline with mocked agents emits ReportEvent and records task."""
    from src.events import PipelineEvent, ReportEvent, ErrorEvent
    from src.knowledge.task_store import TaskStore

    # Use a temp dir for task store to avoid polluting project data
    tmp_dir = tempfile.mkdtemp(prefix="mp_test_tasks_")
    try:
        store = TaskStore(store_dir=tmp_dir)

        task_id = f"test_e2e_{int(time.time())}"
        keyword = "测试关键词"
        src_mode = "news"

        store.create(task_id, keyword, src_mode)

        forum = _StubLogManager(task_id)
        monitor = _StubMonitor()
        orch = _make_orchestrator(task_id, keyword, forum, monitor)
        _patch_debate_agents(orch, forum)

        # Collect all events
        events = list(orch.stream_pipeline())

        # ── Assertions ──

        # Must have at least one PipelineEvent and exactly one ReportEvent
        pipeline_events = [e for e in events if isinstance(e, PipelineEvent)]
        report_events = [e for e in events if isinstance(e, ReportEvent)]
        error_events = [e for e in events if isinstance(e, ErrorEvent) and e.fatal]

        assert len(pipeline_events) >= 4, f"Expected ≥4 pipeline events, got {len(pipeline_events)}"
        assert len(report_events) == 1, f"Expected exactly 1 ReportEvent, got {len(report_events)}"
        assert len(error_events) == 0, f"Unexpected fatal errors: {[e.message for e in error_events]}"

        report = report_events[0]
        assert report.keyword == keyword
        assert report.task_id == task_id
        assert report.sentiment_summary.get("total_news") == 1
        assert report.trend_summary.get("trend_direction") == "positive"

        # 红蓝辩论：采集/报告各一次，红蓝双方各两轮（立论 + 反驳）
        orch.collect_agent.run.assert_called_once()
        assert orch.sentiment_agent.run.call_count == 2, "红方应进行立论+反驳两轮"
        assert orch.trend_agent.run.call_count == 2, "蓝方应进行立论+反驳两轮"
        orch.report_agent.run.assert_called_once()

        # TaskStore should have the task
        store.update_status(task_id, "completed")
        task = store.get(task_id)
        assert task is not None
        assert task["status"] == "completed"
        assert task["keyword"] == keyword

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_pipeline_emits_guidance_and_verdict_forum_events():
    """裁判在轮次间输出引导，辩论结束后输出结构化终裁。"""
    from src.events import ForumEvent

    forum = _StubLogManager("test_debate_events")
    monitor = _StubMonitor()
    orch = _make_orchestrator("test_debate_events", "辩论事件测试", forum, monitor)
    _patch_debate_agents(orch, forum)

    events = list(orch.stream_pipeline())
    forum_events = [e for e in events if isinstance(e, ForumEvent)]

    guidance_events = [e for e in forum_events if e.kind == "guidance"]
    verdict_events = [e for e in forum_events if e.kind == "verdict"]

    assert len(guidance_events) == 1, f"Expected 1 guidance event, got {len(guidance_events)}"
    assert len(verdict_events) == 1, f"Expected 1 verdict event, got {len(verdict_events)}"

    guidance = guidance_events[0]
    assert guidance.agent == "HOST" and guidance.role == "judge"
    assert "核心分歧" in guidance.content

    verdict_event = verdict_events[0]
    # 终裁 LLM 不可用 → 走启发式降级裁定，字段必须完整
    verdict = verdict_event.verdict
    assert verdict.get("stance") in ("negative", "neutral", "positive")
    assert 0.0 <= verdict.get("confidence", -1) <= 1.0
    assert verdict.get("action_signal") in ("watch_out", "neutral", "buy_attention")
    assert "【终裁】" in verdict_event.content


def test_pipeline_second_round_rebuts_opponent():
    """第二轮发言必须携带对方上一轮观点（反驳而非重复立论）。"""
    forum = _StubLogManager("test_rebuttal")
    monitor = _StubMonitor()
    orch = _make_orchestrator("test_rebuttal", "反驳测试", forum, monitor)
    _patch_debate_agents(orch, forum)

    list(orch.stream_pipeline())

    sentiment_calls = orch.sentiment_agent.run.call_args_list
    trend_calls = orch.trend_agent.run.call_args_list
    assert len(sentiment_calls) == 2 and len(trend_calls) == 2

    # 红方第二轮收到的是蓝方立论（run 以位置字典传参）
    red_feedback = sentiment_calls[1].args[0].get("feedback", "")
    assert "蓝方" in red_feedback and "蓝方第1轮发言" in red_feedback
    # 蓝方第二轮收到的是红方反驳
    blue_feedback = trend_calls[1].args[0].get("feedback", "")
    assert "红方" in blue_feedback and "红方第2轮发言" in blue_feedback

    # 双方第二轮发言都应 recorded 且标明是反驳轮
    last_speeches = {}
    for m in forum.get_all_messages():
        if m["agent"] in ("SentimentAgent", "TrendAgent"):
            last_speeches[m["agent"]] = m["content"]
    assert last_speeches["SentimentAgent"].startswith("红方第2轮发言")
    assert last_speeches["TrendAgent"].startswith("蓝方第2轮发言")
    assert "驳斥" in last_speeches["SentimentAgent"]
    assert "驳斥" in last_speeches["TrendAgent"]


def test_pipeline_e2e_collect_failure_produces_fatal_error():
    """When CollectAgent fails, pipeline should emit a fatal ErrorEvent."""
    from src.events import ErrorEvent

    forum = _StubLogManager("test_fail")
    monitor = _StubMonitor()
    orch = _make_orchestrator("test_fail", "失败测试", forum, monitor)

    orch.collect_agent.run = MagicMock(return_value={
        "status": "error", "agent": "CollectAgent",
        "summary": "所有搜索源均未返回真实数据", "data": {},
    })

    events = list(orch.stream_pipeline())

    fatal_errors = [e for e in events if isinstance(e, ErrorEvent) and e.fatal]
    assert len(fatal_errors) >= 1, "Expected at least one fatal ErrorEvent on collect failure"


def test_pipeline_blocking_run_pipeline():
    """OrchestratorAgent.run_pipeline() should return a success dict."""
    forum = _StubLogManager("test_blocking")
    monitor = _StubMonitor()
    orch = _make_orchestrator("test_blocking", "阻塞测试", forum, monitor)
    _patch_debate_agents(orch, forum)

    result = orch.run_pipeline()

    assert result["status"] == "success"
    report_data = result["data"]["report_data"]
    assert report_data["keyword"] == "阻塞测试"
    assert "sentiment_summary" in report_data
    assert "trend_summary" in report_data
    assert "verdict" in report_data
