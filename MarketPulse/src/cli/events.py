"""Events that flow from orchestrator → TUI via post_message bridge."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PipelineEvent:
    """Agent lifecycle events yielded by orchestrator.run_pipeline()."""
    type: str          # agent_start | agent_progress | agent_done | agent_error
    agent: str         # CollectAgent | SentimentAgent | TrendAgent | ReportAgent
    progress: int = 0  # 0-100
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ForumEvent:
    """A single forum message from an agent or host."""
    speaker: str       # CollectAgent | SentimentAgent | TrendAgent | ReportAgent | HOST | SYSTEM
    round_num: int
    content: str


@dataclass
class ReportEvent:
    """Final report payload, emitted once at pipeline completion."""
    task_id: str
    keyword: str
    conclusion: str
    sentiment_summary: Dict[str, Any] = field(default_factory=dict)
    trend_summary: Dict[str, Any] = field(default_factory=dict)
    nodes: List[Dict[str, Any]] = field(default_factory=list)
    edges: List[Dict[str, Any]] = field(default_factory=list)
    ai_insights: Optional[Dict[str, Any]] = None
    graph_insights: Optional[Dict[str, Any]] = None
    causal_chains: List[str] = field(default_factory=list)
    graph_html_path: str = ""
    forum_debate: List[Dict[str, Any]] = field(default_factory=list)
    analyzed_news: List[Dict[str, Any]] = field(default_factory=list)
    collect_meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ErrorEvent:
    """Non-fatal or fatal error during pipeline execution."""
    stage: str
    message: str
    fatal: bool = False
