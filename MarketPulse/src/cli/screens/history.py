"""Past task browser screen."""

import os
import webbrowser

from textual.screen import Screen
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import DataTable, Static

from ...knowledge.task_store import TaskStore
from ... import config as cfg


class HistoryScreen(Screen):
    """Browse past analysis tasks and re-run or view reports."""

    BINDINGS = [
        ("escape", "back", "返回"),
        ("enter", "view_task", "查看详情"),
        ("v", "view_report", "打开报告"),
        ("g", "open_graph", "打开图谱"),
        ("r", "rerun", "重新分析"),
    ]

    CSS = """
    HistoryScreen {
        background: #0d1117;
    }

    #history-title {
        dock: top;
        height: 3;
        padding: 1 2;
        background: #161b22;
        color: #58a6ff;
        text-style: bold;
    }

    #history-body {
        height: 1fr;
    }

    #history-table {
        width: 50%;
        margin: 1;
    }

    #history-detail {
        width: 1fr;
        margin: 1 1 1 0;
        padding: 1 2;
        border: solid #30363d;
        background: #161b22;
    }

    #history-footer {
        dock: bottom;
        height: 1;
    }

    DataTable {
        background: #161b22;
        color: #c9d1d9;
    }

    DataTable > .datatable--header {
        background: #21262d;
        color: #58a6ff;
    }
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tasks: list[dict] = []
        self._store = TaskStore()
        self._config = cfg.init_config()

    def compose(self) -> ComposeResult:
        yield Static("📋  历史分析任务  │  Enter 查看  │  V 打开报告  │  G 打开图谱  │  R 重新分析  │  Esc 返回", id="history-title")
        with Horizontal(id="history-body"):
            yield DataTable(id="history-table")
            yield Static("", id="history-detail")
        yield Static("", id="history-footer")

    def on_mount(self):
        table = self.query_one("#history-table", DataTable)
        table.add_columns("关键词", "状态", "时间", "ID")

        self._tasks = self._store.list_recent(50)
        for t in self._tasks:
            status_icon = {"completed": "✅", "error": "❌", "running": "⏳", "abandoned": "⚠️"}.get(
                t.get("status", ""), "❓"
            )
            created = t.get("created_at", "")[:19]  # truncate TZ
            table.add_row(
                t.get("keyword", "?"),
                f"{status_icon} {t.get('status', '?')}",
                created,
                t.get("task_id", "")[-12:],
                key=t.get("task_id", ""),
            )

        if self._tasks:
            table.focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        row_key = getattr(event, "row_key", None)
        if not row_key:
            return
        task = next((t for t in self._tasks if t["task_id"] == row_key.value), None)
        if not task:
            return

        detail = self.query_one("#history-detail", Static)
        report_path = os.path.join(cfg.results_dir(), "reports", f"{task['task_id']}.html")
        graph_path = os.path.join(cfg.results_dir(), "reports", f"{task['task_id']}_graph.html")

        lines = [
            f"[bold cyan]{task.get('keyword', '?')}[/bold cyan]",
            "",
            f"状态: {task.get('status', '?')}",
            f"模式: {task.get('src_mode', 'news')}",
            f"时间: {task.get('created_at', '?')[:19]}",
            f"ID: {task['task_id']}",
            "",
        ]

        if os.path.exists(report_path):
            lines.append("[green]报告文件 ✓[/green]")
        else:
            lines.append("[dim]报告文件 ✗[/dim]")
        if os.path.exists(graph_path):
            lines.append("[green]图谱文件 ✓[/green]")
        else:
            lines.append("[dim]图谱文件 ✗[/dim]")

        if task.get("error"):
            lines.extend(["", f"[red]错误: {task['error']}[/red]"])

        detail.update("\n".join(lines))
        self._selected_task = task

    def action_back(self):
        self.dismiss()

    def action_view_task(self):
        task = getattr(self, "_selected_task", None)
        if not task:
            return
        report_path = os.path.join(cfg.results_dir(), "reports", f"{task['task_id']}.html")
        if os.path.exists(report_path):
            webbrowser.open(f"file://{os.path.abspath(report_path)}")
            self.notify(f"打开报告: {task['keyword']}", title="Report")

    def action_view_report(self):
        self.action_view_task()

    def action_open_graph(self):
        task = getattr(self, "_selected_task", None)
        if not task:
            return
        graph_path = os.path.join(cfg.results_dir(), "reports", f"{task['task_id']}_graph.html")
        if os.path.exists(graph_path):
            webbrowser.open(f"file://{os.path.abspath(graph_path)}")
            self.notify(f"打开图谱: {task['keyword']}", title="Graph")
        else:
            self.notify("该任务没有图谱文件", severity="warning", title="Graph")

    def action_rerun(self):
        task = getattr(self, "_selected_task", None)
        if not task:
            return
        self.dismiss()
        app = self.app
        if hasattr(app, "start_analysis"):
            app.start_analysis(task["keyword"])
