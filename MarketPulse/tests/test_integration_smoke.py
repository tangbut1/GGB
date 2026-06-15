"""Real integration tests that verify actual system behavior, bypassing mocks."""

import pytest
import os
import shutil
import tempfile

@pytest.mark.integration
def test_real_pipeline_without_keys():
    """Run the pipeline end-to-end without valid API keys.
    
    Verifies that the system gracefully handles the failure
    and emits appropriate ErrorEvents instead of crashing.
    """
    from src.agents.orchestrator import OrchestratorAgent
    from src.forum.log_manager import LogManager
    from src.forum.monitor import ForumMonitor
    from src.cli.events import ErrorEvent, ReportEvent

    # Use a temp directory to avoid polluting actual project data
    tmp_dir = tempfile.mkdtemp()
    try:
        # Override config to use a dummy/invalid API key
        config = {
            "agent_llm": {
                "collect_agent": {"api_key": "invalid_key", "base_url": "https://api.openai.com/v1"},
                "sentiment_agent": {"api_key": "invalid_key", "base_url": "https://api.openai.com/v1"},
                "trend_agent": {"api_key": "invalid_key", "base_url": "https://api.openai.com/v1"},
                "report_agent": {"api_key": "invalid_key", "base_url": "https://api.openai.com/v1"},
                "forum_host": {"api_key": "invalid_key", "base_url": "https://api.openai.com/v1"},
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

        # Without a valid API key (and assuming the search providers might also fail
        # or the LLM call immediately fails), we expect the pipeline to emit an ErrorEvent
        # and NOT crash or pretend to succeed.
        
        errors = [e for e in events if isinstance(e, ErrorEvent)]
        reports = [e for e in events if isinstance(e, ReportEvent)]
        
        # It's highly likely it emits a fatal ErrorEvent from CollectAgent if no search results
        # are returned, OR if an LLM is called, it will throw an auth error.
        assert len(errors) > 0, "Expected at least one ErrorEvent due to missing/invalid keys."

        assert len(reports) == 0, "Should not produce a valid ReportEvent on failure."
        
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
