"""End-to-end pipeline test using mock agents.

Verifies the full orchestrator flow: event generation, TaskStore persistence,
and report path construction — without any real network or LLM calls.
"""

import os
import time
import tempfile
import shutil
from unittest.mock import MagicMock, patch

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


# ---------------------------------------------------------------------------
# Minimal no-op Forum / Monitor stubs
# ---------------------------------------------------------------------------

class _StubLogManager:
    def __init__(self, task_id: str):
        self.task_id = task_id
        self._lines: list[str] = []

    def write(self, agent_name, iteration, content):
        self._lines.append(f"[{agent_name}] {content}")

    def read_all_lines(self):
        return list(self._lines)

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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_pipeline_e2e_produces_report_event():
    """Full pipeline with mocked agents emits ReportEvent and records task."""
    from src.agents.orchestrator import OrchestratorAgent
    from src.cli.events import PipelineEvent, ReportEvent, ErrorEvent
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

        config = {
            "agent_llm": {
                "collect_agent": {},
                "sentiment_agent": {},
                "trend_agent": {},
                "report_agent": {},
                "forum_host": {},
            }
        }

        orch = OrchestratorAgent(
            task_id=task_id,
            keyword=keyword,
            config=config,
            forum_manager=forum,
            monitor=monitor,
            src_mode=src_mode,
        )

        # Patch all agent run methods to return mock data
        orch.collect_agent.run = MagicMock(return_value=_COLLECT_RESULT)
        orch.sentiment_agent.run = MagicMock(return_value=_SENTIMENT_RESULT)
        orch.trend_agent.run = MagicMock(return_value=_TREND_RESULT)
        orch.report_agent.run = MagicMock(return_value=_REPORT_RESULT)

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

        # All 4 agents should have been called exactly once
        orch.collect_agent.run.assert_called_once()
        orch.sentiment_agent.run.assert_called_once()
        orch.trend_agent.run.assert_called_once()
        orch.report_agent.run.assert_called_once()

        # TaskStore should have the task
        store.update_status(task_id, "completed")
        task = store.get(task_id)
        assert task is not None
        assert task["status"] == "completed"
        assert task["keyword"] == keyword

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_pipeline_e2e_collect_failure_produces_fatal_error():
    """When CollectAgent fails, pipeline should emit a fatal ErrorEvent."""
    from src.agents.orchestrator import OrchestratorAgent
    from src.cli.events import ErrorEvent

    forum = _StubLogManager("test_fail")
    monitor = _StubMonitor()
    config = {"agent_llm": {"collect_agent": {}, "sentiment_agent": {}, "trend_agent": {}, "report_agent": {}, "forum_host": {}}}

    orch = OrchestratorAgent(
        task_id="test_fail", keyword="失败测试", config=config,
        forum_manager=forum, monitor=monitor, src_mode="news",
    )

    orch.collect_agent.run = MagicMock(return_value={
        "status": "error", "agent": "CollectAgent",
        "summary": "所有搜索源均未返回真实数据", "data": {},
    })

    events = list(orch.stream_pipeline())

    fatal_errors = [e for e in events if isinstance(e, ErrorEvent) and e.fatal]
    assert len(fatal_errors) >= 1, "Expected at least one fatal ErrorEvent on collect failure"


def test_pipeline_blocking_run_pipeline():
    """OrchestratorAgent.run_pipeline() should return a success dict."""
    from src.agents.orchestrator import OrchestratorAgent

    forum = _StubLogManager("test_blocking")
    monitor = _StubMonitor()
    config = {"agent_llm": {"collect_agent": {}, "sentiment_agent": {}, "trend_agent": {}, "report_agent": {}, "forum_host": {}}}

    orch = OrchestratorAgent(
        task_id="test_blocking", keyword="阻塞测试", config=config,
        forum_manager=forum, monitor=monitor, src_mode="news",
    )

    orch.collect_agent.run = MagicMock(return_value=_COLLECT_RESULT)
    orch.sentiment_agent.run = MagicMock(return_value=_SENTIMENT_RESULT)
    orch.trend_agent.run = MagicMock(return_value=_TREND_RESULT)
    orch.report_agent.run = MagicMock(return_value=_REPORT_RESULT)

    result = orch.run_pipeline()

    assert result["status"] == "success"
    report_data = result["data"]["report_data"]
    assert report_data["keyword"] == "阻塞测试"
    assert "sentiment_summary" in report_data
    assert "trend_summary" in report_data


@pytest.mark.anyio
async def test_app_taskstore_integration():
    """Verify that MarketPulseApp correctly interacts with TaskStore during its lifecycle."""
    from src.cli.app import MarketPulseApp
    from src.cli.events import ReportEvent, ErrorEvent

    app = MarketPulseApp()
    
    # We use Textual's run_test context to mount the app and its screens
    async with app.run_test() as pilot:
        # Replace the real task store with a mock
        mock_store = MagicMock()
        app._task_store = mock_store
        
        # Patch OrchestratorAgent so we don't run real searches in the worker thread
        with patch("src.cli.app.OrchestratorAgent") as mock_orch:
            mock_instance = mock_orch.return_value
            mock_instance.stream_pipeline.return_value = []
            
            # 1. Trigger start_analysis
            app.start_analysis("苹果手机", "social")
            
            # Wait a tick for UI updates
            await pilot.pause(0.1)
            
            # TaskStore.create should have been called
            mock_store.create.assert_called_once()
            args = mock_store.create.call_args[0]
            assert args[1] == "苹果手机"
            assert args[2] == "social"
            task_id = args[0]
            assert task_id.startswith("task_")
            
            # 2. Simulate ReportEvent
            report_event = ReportEvent(
                keyword="苹果手机",
                task_id=task_id,
                conclusion="Test Conclusion",
                causal_chains=[],
                graph_html_path=""
            )
            app._handle_event(report_event)
            mock_store.update_status.assert_called_with(task_id, "completed")
            
            # 3. Simulate Fatal ErrorEvent
            error_event = ErrorEvent(stage="pipeline", message="Network Error", fatal=True)
            app._handle_event(error_event)
            mock_store.update_status.assert_called_with(task_id, "error", "Network Error")
            
            # 4. Simulate Cancellation
            app.action_cancel_analysis()
            mock_store.update_status.assert_called_with(task_id, "cancelling")
            
            # 5. Simulate Orchestrator emitting cancellation event
            cancel_event = ErrorEvent(stage="pipeline", message="任务已手动取消", fatal=True)
            app._handle_event(cancel_event)
            mock_store.update_status.assert_called_with(task_id, "cancelled", "任务已手动取消")
