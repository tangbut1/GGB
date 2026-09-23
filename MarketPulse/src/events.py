"""Pipeline event contracts — decouples the analysis kernel from any UI.

The orchestrator yields these events from ``stream_pipeline()``; the Flask
layer (``app.py``) translates them into SocketIO emissions. Keeping them as
plain dataclasses means no UI framework is imported by the kernel.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PipelineEvent:
    """One stage transition of an agent in the pipeline.

    ``content`` carries the agent's debate speech (if any) so the UI can
    render the round without re-parsing the forum log.
    """

    stage: str                       # collect | sentiment | trend | report
    agent: str                       # CollectAgent | SentimentAgent | ...
    status: str                      # active | done | err
    progress: int = 0
    message: str = ""
    role: str = ""                   # collect | red | blue | judge | report
    round: int = 0                   # debate round number (0 = not a debate turn)
    content: str = ""                # debate speech text

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage": self.stage,
            "agent": self.agent,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "role": self.role,
            "round": self.round,
            "content": self.content,
        }


@dataclass
class ForumEvent:
    """A forum/HOST turn: judge guidance between rounds or the final verdict."""

    agent: str = "HOST"
    role: str = "judge"
    round: int = 0
    content: str = ""
    kind: str = "guidance"           # guidance | verdict
    verdict: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "HOST",
            "agent": self.agent,
            "role": self.role,
            "round": self.round,
            "content": self.content,
            "kind": self.kind,
            "verdict": self.verdict,
        }


@dataclass
class ReportEvent:
    """Terminal event: the full report payload."""

    keyword: str = ""
    task_id: str = ""
    conclusion: str = ""
    causal_chains: List[Any] = field(default_factory=list)
    graph_html_path: str = ""
    sentiment_summary: Dict[str, Any] = field(default_factory=dict)
    trend_summary: Dict[str, Any] = field(default_factory=dict)
    verdict: Dict[str, Any] = field(default_factory=dict)
    report_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ErrorEvent:
    """A stage failure. ``fatal=True`` aborts the pipeline."""

    stage: str = ""
    message: str = ""
    fatal: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {"stage": self.stage, "message": self.message, "fatal": self.fatal}
