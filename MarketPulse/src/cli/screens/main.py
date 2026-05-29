"""Main split-screen layout for the console workstation."""

from textual.screen import Screen
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Input, Static

from ..widgets import (
    HeaderWidget,
    AgentPanel,
    ForumPanel,
    InsightPanel,
    FooterWidget,
)


class MainScreen(Screen):
    """Primary workstation screen with keyword input, agent status, forum, and insights."""

    CSS = """
    .textual-dark MainScreen { background: #1e1e1e; color: #d4d4d4; }
    .textual-dark #header-area { background: #2d2d2d; border-bottom: solid #58a6ff; }
    .textual-dark #left-panel { border: round #58a6ff; }
    .textual-dark #forum-area { border: round #58a6ff; }
    .textual-dark #insight-area { border: round #58a6ff; }
    .textual-dark #footer-area { background: #2d2d2d; color: #d4d4d4; }
    .textual-dark #keyword-input { border: solid #58a6ff; background: #252526; color: #d4d4d4; }
    .textual-dark #keyword-label { color: #00f0ff; }
    .textual-dark Input:focus { border: double #00f0ff; }

    .textual-light MainScreen { background: #fdf6e3; color: #657b83; }
    .textual-light #header-area { background: #eee8d5; border-bottom: solid #93a1a1; }
    .textual-light #left-panel { border: round #93a1a1; }
    .textual-light #forum-area { border: round #93a1a1; }
    .textual-light #insight-area { border: round #93a1a1; }
    .textual-light #footer-area { background: #eee8d5; color: #657b83; }
    .textual-light #keyword-input { border: solid #93a1a1; background: #fdf6e3; color: #657b83; }
    .textual-light #keyword-label { color: #268bd2; }
    .textual-light Input:focus { border: double #268bd2; }

    #header-area { dock: top; height: 3; padding: 0 1; }
    #body-area { height: 1fr; padding: 1 2; }
    #left-panel { width: 30; padding: 0 1 0 0; }
    #right-panel { width: 1fr; }
    #forum-area { height: 1fr; margin-bottom: 1; }
    #insight-area { height: auto; max-height: 18; }
    #footer-area { dock: bottom; height: 1; }
    #keyword-input { dock: top; height: 3; margin: 1 2; }
    #keyword-label { text-style: bold; margin: 1 0 0 3; }
    """

    def compose(self) -> ComposeResult:
        yield HeaderWidget(id="header-area")
        yield Static("输入关键词后按 Enter 开始分析", id="keyword-label")
        yield Input(placeholder="输入品牌或话题关键词...", id="keyword-input")
        with Horizontal(id="body-area"):
            yield AgentPanel(id="left-panel")
            with Vertical(id="right-panel"):
                yield ForumPanel(id="forum-area")
                yield InsightPanel(id="insight-area")
        yield FooterWidget(id="footer-area")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        keyword = event.value.strip()
        if keyword:
            self.query_one("#keyword-label", Static).update(f"分析中: [bold cyan]{keyword}[/bold cyan]")
            self.query_one("#keyword-input", Input).display = False
            # Delegate to app to start analysis
            if hasattr(self.app, "start_analysis"):
                self.app.start_analysis(keyword)

    def show_ready(self):
        """Reset UI for a new query."""
        inp = self.query_one("#keyword-input", Input)
        inp.display = True
        inp.value = ""
        inp.focus()
        self.query_one("#keyword-label", Static).update("输入关键词后按 Enter 开始分析")
        # Reset agent panel states
        agent_panel = self.query_one("#left-panel")
        for agent in agent_panel.AGENTS:
            agent_panel.set_agent(agent, "idle")
