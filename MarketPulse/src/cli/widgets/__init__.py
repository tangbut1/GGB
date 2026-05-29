"""TUI widgets for the MarketPulse console workstation."""

from textual.widgets import Static
from rich.text import Text
from rich.table import Table
from rich.panel import Panel
from rich.console import RenderableType
from rich import box
from datetime import datetime


class HeaderWidget(Static):
    """Top bar: keyword, progress, elapsed time."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._keyword = ""
        self._progress = 0
        self._label = "就绪"
        self._start_time = None

    def set_keyword(self, kw: str):
        self._keyword = kw
        self._start_time = datetime.now()
        self.refresh()

    def set_progress(self, pct: int, label: str = ""):
        self._progress = pct
        if label:
            self._label = label
        self.refresh()

    def render(self) -> RenderableType:
        bar_width = 40
        filled = int(bar_width * self._progress / 100)
        bar = "━" * filled + "╸" * (bar_width - filled)

        elapsed = ""
        if self._start_time:
            secs = int((datetime.now() - self._start_time).total_seconds())
            elapsed = f" {secs // 60:02d}:{secs % 60:02d}"

        kw_display = self._keyword or "等待输入..."
        text = Text()
        text.append(f"  MarketPulse  ", style="bold reverse")
        text.append(f" {kw_display} ", style="bold italic")
        text.append(f"{elapsed}  \n", style="dim")
        text.append(f"  {bar} ")
        text.append(f"{self._progress}% ", style="bold")
        text.append(f"{self._label}", style="italic dim")
        return text


class AgentPanel(Static):
    """Left sidebar showing agent statuses."""

    AGENTS = ["CollectAgent", "SentimentAgent", "TrendAgent", "ReportAgent"]
    ICONS = {"idle": "○", "active": "●", "done": "✓", "error": "✗"}

    def on_mount(self):
        self.border_title = "Agents"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._states = {a: "idle" for a in self.AGENTS}

    def set_agent(self, name: str, state: str):
        if name in self._states:
            self._states[name] = state
            self.refresh()

    def render(self) -> RenderableType:
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("icon", width=2)
        table.add_column("name", width=16)
        table.add_column("status", width=10)

        colors = {"idle": "dim", "active": "bold yellow", "done": "bold green", "error": "bold red"}
        labels = {"idle": "等待", "active": "运行中", "done": "完成", "error": "失败"}

        for agent in self.AGENTS:
            state = self._states[agent]
            icon = self.ICONS[state]
            color = colors[state]
            label = labels[state]
            short = agent.replace("Agent", "")
            table.add_row(icon, short, label, style=color)

        return table


class ForumPanel(Static):
    """Live forum debate stream — auto-scrolling log view."""

    def on_mount(self):
        self.border_title = "Forum Live"

    def __init__(self, *args, max_lines: int = 100, **kwargs):
        super().__init__(*args, **kwargs)
        self._lines: list[str] = []
        self._max_lines = max_lines

    def add_line(self, speaker: str, content: str):
        from rich.markup import escape
        content = escape(content)
        timestamp = datetime.now().strftime("%H:%M:%S")
        color = {
            "CollectAgent": "cyan", "SentimentAgent": "magenta",
            "TrendAgent": "yellow", "ReportAgent": "green",
            "HOST": "bold", "SYSTEM": "dim",
        }.get(speaker, "")
        if color:
            self._lines.append(f"[{timestamp}] [{color}]{speaker}[/{color}] {content}")
        else:
            self._lines.append(f"[{timestamp}] {speaker} {content}")
        if len(self._lines) > self._max_lines:
            self._lines = self._lines[-self._max_lines:]
        self.refresh()

    def render(self) -> RenderableType:
        if not self._lines:
            return "等待 Agent 发言..."
        return Text.from_markup("\n".join(self._lines[-20:]))


class InsightPanel(Static):
    """Bottom panel: AI insights, causal chains, and follow-up prompt."""

    def on_mount(self):
        self.border_title = "Insights"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._causal_chains: list[str] = []
        self._conclusion = ""
        self._keyword = ""

    def set_result(self, keyword: str, conclusion: str, causal_chains: list[str]):
        self._keyword = keyword
        self._conclusion = conclusion
        self._causal_chains = causal_chains
        self.refresh()

    def render(self) -> RenderableType:
        from rich.markup import escape
        parts = []
        if self._conclusion:
            parts.append(f"[bold]结论:[/bold] {escape(self._conclusion)}\n")
        if self._causal_chains:
            parts.append("[bold]因果关系链:[/bold]")
            for chain in self._causal_chains:
                parts.append(f"  {escape(chain)}")
        if not parts:
            return "等待分析结果..."
        return Text.from_markup("\n".join(parts))


class FooterWidget(Static):
    """Keybindings hint bar."""

    def render(self) -> RenderableType:
        keys = [
            ("Enter", "开始分析"),
            ("H", "历史"),
            ("G", "图谱"),
            ("R", "报告"),
            ("Q", "追问"),
            ("T", "切换主题"),
            ("Ctrl+C", "退出"),
        ]
        parts = ["  " + "  │  ".join(f"[bold]{k}[/bold] {v}" for k, v in keys) + "  "]
        return Text.from_markup("".join(parts))
