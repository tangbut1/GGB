"""Real integration tests that verify actual system behavior, bypassing mocks.

These tests hit real external services (search providers, LLM endpoints) and
are therefore marked ``integration``; run them explicitly with::

    python -m pytest tests/test_integration_smoke.py -m integration
"""

import pytest
import shutil
import tempfile

# 占位符凭据：仅用于验证“密钥无效时系统优雅降级”，不是任何真实密钥
_PLACEHOLDER_KEY = "invalid-placeholder-key"
_ENDPOINT = "https://api.openai.com/v1"
_AGENT_NAMES = ("collect_agent", "sentiment_agent", "trend_agent",
                "report_agent", "forum_host")

@pytest.mark.integration
def test_real_pipeline_without_keys():
    """Run the pipeline end-to-end without valid API keys.

    The debate architecture degrades gracefully instead of crashing:
    - hard failure (no search results) → fatal ErrorEvent, no report;
    - LLM unavailable → local fallbacks (SnowNLP / Prophet / heuristic
      verdict) and the pipeline still completes with a fallback verdict.
    Either outcome is acceptable; a crash or a fabricated success is not.
    """
    from src.agents.orchestrator import OrchestratorAgent
    from src.forum.log_manager import LogManager
    from src.forum.monitor import ForumMonitor
    from src.events import ErrorEvent, ReportEvent

    tmp_dir = tempfile.mkdtemp()
    try:
        # Override config to use a dummy/invalid API key
        config = {
            "agent_llm": {
                name: {"api_key": _PLACEHOLDER_KEY, "base_url": _ENDPOINT}
                for name in _AGENT_NAMES
            }
        }

        task_id = "test_smoke_no_keys"
        keyword = "IntegrationTest"

        forum_manager = LogManager(task_id)
        monitor = ForumMonitor(forum_manager, config)
        forum_manager.set_monitor(monitor)

        orchestrator = OrchestratorAgent(
            task_id=task_id,
            keyword=keyword,
            config=config,
            forum_manager=forum_manager,
            monitor=monitor,
            src_mode="news"
        )

        monitor.start()
        try:
            events = list(orchestrator.stream_pipeline())
        finally:
            monitor.stop()

        errors = [e for e in events if isinstance(e, ErrorEvent)]
        reports = [e for e in events if isinstance(e, ReportEvent)]
        fatal_errors = [e for e in errors if e.fatal]

        if fatal_errors:
            # 采集阶段硬失败：任务终止，不得产出报告
            assert len(reports) == 0, "采集失败时不应产出 ReportEvent"
        else:
            # 降级模式：流水线走完，终裁为启发式兜底（非 LLM 生成）
            assert len(reports) == 1, "LLM 降级时流水线仍应完成并产出唯一报告"
            verdict = reports[0].verdict
            assert verdict.get("stance") in ("negative", "neutral", "positive")
            assert verdict.get("action_signal") in ("watch_out", "neutral", "buy_attention")
            assert 0.0 <= verdict.get("confidence", -1) <= 1.0
            # 无效 key 下裁判 LLM 必然失败 → 兜底裁定必须自报身份
            assert "裁判 LLM" in verdict.get("summary", ""), \
                "无效 API Key 下的终裁必须是启发式兜底，不得伪装成 LLM 裁定"

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
