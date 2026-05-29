"""Textual App — main entry point for the MarketPulse console workstation."""

import os
import threading
import webbrowser
from typing import Union

from textual.app import App
from textual.worker import Worker, WorkerState

from .. import config as cfg
from ..agents.orchestrator import OrchestratorAgent
from ..forum.log_manager import LogManager
from ..forum.monitor import ForumMonitor
from ..cli.events import PipelineEvent, ForumEvent, ReportEvent, ErrorEvent
from .screens.main import MainScreen
from .screens.followup import FollowupModal
from .screens.history import HistoryScreen
from .widgets import HeaderWidget, AgentPanel, ForumPanel, InsightPanel


class MarketPulseApp(App):
    """Console workstation for multi-agent market sentiment analysis."""

    TITLE = "MarketPulse"
    SUB_TITLE = "Multi-Agent Console Workstation"

    BINDINGS = [
        ("ctrl+c", "quit", "退出"),
        ("g", "open_graph", "打开图谱"),
        ("r", "view_report", "查看报告"),
        ("q", "followup", "追问AI"),
        ("h", "open_history", "历史任务"),
        ("t", "toggle_dark", "切换主题"),
    ]

    def __init__(self, config_override: dict | None = None):
        super().__init__()
        self._config = config_override or cfg.init_config()
        self._task_id: str = ""
        self._keyword: str = ""
        self._graph_path: str = ""
        self._report_path: str = ""
        self._pipeline_worker: Worker | None = None

    def on_mount(self):
        self.push_screen(MainScreen())

    # ── Pipeline orchestration ──────────────────────────────────

    def start_analysis(self, keyword: str):
        """Called from MainScreen when user submits a keyword."""
        import time
        self._keyword = keyword
        self._task_id = f"task_{int(time.time())}"

        screen = self.screen
        header = screen.query_one("#header-area")

        header.set_keyword(keyword)
        header.set_progress(0, "初始化...")

        # Set up forum
        forum_manager = LogManager(self._task_id)
        monitor = ForumMonitor(forum_manager, self._config)
        forum_manager.set_monitor(monitor)

        # Create orchestrator
        orchestrator = OrchestratorAgent(
            task_id=self._task_id,
            keyword=keyword,
            config=self._config,
            forum_manager=forum_manager,
            monitor=monitor,
            src_mode="news",
        )

        # Store for cancel
        self._orchestrator = orchestrator

        # Start monitor + pipeline in worker thread
        monitor.start()

        def run_and_post():
            try:
                for event in orchestrator.stream_pipeline():
                    self.call_from_thread(self._handle_event, event)
                monitor.stop()
            except Exception as exc:
                self.call_from_thread(
                    self._handle_event,
                    ErrorEvent(stage="pipeline", message=str(exc), fatal=True)
                )
                try:
                    monitor.stop()
                except Exception:
                    pass

        self._pipeline_worker = self.run_worker(
            run_and_post, thread=True, exclusive=True
        )

    # ── Event dispatch ──────────────────────────────────────────

    def _handle_event(self, event: Union[PipelineEvent, ForumEvent, ReportEvent, ErrorEvent]):
        """Dispatch events from worker thread to widget updates. Runs on UI thread."""
        try:
            screen = self.screen
            header = screen.query_one("#header-area")
            agent_panel = screen.query_one("#left-panel")
            forum_panel = screen.query_one("#forum-area")
            insight_panel = screen.query_one("#insight-area")
        except Exception:
            return  # Screen not mounted

        if isinstance(event, PipelineEvent):
            if event.type == "agent_start":
                agent_panel.set_agent(event.agent, "active")
                header.set_progress(event.progress, f"{event.agent} 运行中...")
            elif event.type == "agent_done":
                agent_panel.set_agent(event.agent, "done")
                news_count = event.data.get("news_count", 0)
                label = f"{event.agent} 完成"
                if news_count:
                    label += f" ({news_count}条)"
                header.set_progress(event.progress, label)
            elif event.type == "agent_error":
                agent_panel.set_agent(event.agent, "error")
                header.set_progress(event.progress, f"{event.agent} 失败")

        elif isinstance(event, ForumEvent):
            forum_panel.add_line(event.speaker, event.content)

        elif isinstance(event, ErrorEvent):
            if event.fatal:
                header.set_progress(0, f"错误: {event.message}")
                if hasattr(self.screen, "show_ready"):
                    self.screen.show_ready()

        elif isinstance(event, ReportEvent):
            agent_panel.set_agent("ReportAgent", "done")
            header.set_progress(100, "完成")
            insight_panel.set_result(
                event.keyword, event.conclusion, event.causal_chains
            )
            self._graph_path = event.graph_html_path
            self._report_path = os.path.join(
                f"{cfg.results_dir()}/reports", f"{event.task_id}.html"
            )
            # Re-enable input for next query
            if hasattr(self.screen, "show_ready"):
                self.screen.show_ready()

    # ── Keybindings ─────────────────────────────────────────────

    def action_open_graph(self):
        """Open the event graph HTML in the default browser."""
        if self._graph_path and os.path.exists(self._graph_path):
            webbrowser.open(f"file://{self._graph_path}")
            self.notify(f"打开图谱: {self._graph_path}", title="Graph")
        else:
            self.notify("图谱尚未生成或不可用", title="Graph", severity="warning")

    def action_view_report(self):
        """Open the HTML report in the default browser."""
        if self._report_path and os.path.exists(self._report_path):
            webbrowser.open(f"file://{self._report_path}")
            self.notify(f"打开报告: {self._report_path}", title="Report")
        else:
            self.notify("报告尚未生成或不可用", title="Report", severity="warning")

    def action_followup(self):
        """Open the follow-up Q&A modal."""
        if not self._keyword or not self._report_path:
            self.notify("请先完成一次分析后再追问", title="Follow-up", severity="warning")
            return

        # Use forum_host config for follow-up LLM calls
        llm_config = self._config.get("agent_llm", {}).get("forum_host", {})
        if not llm_config.get("api_key"):
            self.notify("API Key 未配置，无法追问", title="Follow-up", severity="error")
            return

        # Get the latest conclusion from the insight panel
        try:
            screen = self.screen
            insight = screen.query_one("#insight-area")
            conclusion = insight._conclusion or "分析已完成"
        except Exception:
            conclusion = "分析已完成"

        self.push_screen(FollowupModal(self._keyword, conclusion, llm_config))

    def action_open_history(self):
        """Open the task history browser."""
        self.push_screen(HistoryScreen())
