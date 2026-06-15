"""Tests for the Headless CLI mode."""

from unittest.mock import MagicMock, patch

def test_cli_headless_success():
    """Verify _run_headless returns 0 when pipeline completes successfully."""
    from src.cli.app import _run_headless
    from src.cli.events import ReportEvent

    # Mock the orchestrator to yield a single ReportEvent and then stop
    with patch("src.cli.app.OrchestratorAgent") as mock_orch:
        mock_instance = mock_orch.return_value
        report = ReportEvent(
            keyword="Apple",
            task_id="task_123",
            conclusion="Test conclusion",
            causal_chains=[],
            graph_html_path=""
        )
        mock_instance.stream_pipeline.return_value = [report]
        
        # Also need to mock TaskStore to not actually write to disk during unit tests
        with patch("src.cli.app.TaskStore"):
            exit_code = _run_headless("Apple", "news")
            
        assert exit_code == 0


def test_cli_headless_fatal_returns_nonzero():
    """Verify _run_headless returns 1 when a fatal error occurs in the pipeline."""
    from src.cli.app import _run_headless
    from src.cli.events import ErrorEvent

    with patch("src.cli.app.OrchestratorAgent") as mock_orch:
        mock_instance = mock_orch.return_value
        error = ErrorEvent(
            stage="pipeline",
            message="Fatal network error",
            fatal=True
        )
        mock_instance.stream_pipeline.return_value = [error]
        
        with patch("src.cli.app.TaskStore"):
            exit_code = _run_headless("Apple", "news")
            
        assert exit_code == 1
