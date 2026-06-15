"""Tests for TUI screens, like history rerun preserving src_mode."""

import pytest
from unittest.mock import MagicMock, patch

@pytest.mark.anyio
async def test_history_rerun_preserves_src_mode():
    from src.cli.app import MarketPulseApp
    from src.cli.screens.history import HistoryScreen

    app = MarketPulseApp()
    
    # We use Textual's run_test context
    async with app.run_test() as pilot:
        # We need to mock start_analysis on the app
        app.start_analysis = MagicMock()
        
        mock_task = {
            "task_id": "test_social_1",
            "keyword": "特斯拉",
            "src_mode": "social",
            "status": "completed",
            "created_at": "2025-01-01T12:00:00"
        }
        
        # Patch TaskStore where it's instantiated inside history.py
        with patch("src.cli.screens.history.TaskStore") as mock_store_cls:
            mock_store_cls.return_value.list_recent.return_value = [mock_task]
            
            # Now push the screen
            await pilot.app.push_screen(HistoryScreen())
            await pilot.pause(0.1)
            
            screen = pilot.app.screen
            assert isinstance(screen, HistoryScreen)
            
            # Textual Datatable rows can be selected programmatically by focusing and sending enter
            # Or we can just manually set the _selected_task and call action_rerun()
            screen._selected_task = mock_task
            screen.action_rerun()
            
            # Verify app.start_analysis was called with the right arguments
            app.start_analysis.assert_called_once_with("特斯拉", "social")
