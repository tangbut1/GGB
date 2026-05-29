"""
MarketPulse Agents Package
"""
__all__ = [
    "BaseAgent",
    "CollectAgent",
    "SentimentAgent",
    "TrendAgent",
    "ReportAgent",
    "OrchestratorAgent"
]


def __getattr__(name):
    if name == "BaseAgent":
        from .base_agent import BaseAgent
        return BaseAgent
    if name == "CollectAgent":
        from .collect_agent import CollectAgent
        return CollectAgent
    if name == "SentimentAgent":
        from .sentiment_agent import SentimentAgent
        return SentimentAgent
    if name == "TrendAgent":
        from .trend_agent import TrendAgent
        return TrendAgent
    if name == "ReportAgent":
        from .report_agent import ReportAgent
        return ReportAgent
    if name == "OrchestratorAgent":
        from .orchestrator import OrchestratorAgent
        return OrchestratorAgent
    raise AttributeError(name)
