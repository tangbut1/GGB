import time
from typing import Dict, Any, Optional, Generator, Union

from .. import config as cfg
from ..cli.events import PipelineEvent, ForumEvent, ReportEvent, ErrorEvent
from .collect_agent import CollectAgent
from .sentiment_agent import SentimentAgent
from .trend_agent import TrendAgent
from .report_agent import ReportAgent


class OrchestratorAgent:
    """协调各 Agent 执行分析流水线，支持论坛协作模式。

    - stream_pipeline() → generator yielding events (TUI / headless)
    - run_pipeline() → blocking call returning dict (script usage)
    """

    def __init__(self, task_id: str, keyword: str, config: dict,
                 forum_manager, monitor,
                 local_data_path: Optional[str] = None,
                 src_mode: str = "news"):
        self.task_id = task_id
        self.keyword = keyword
        self.config = config
        self.forum_manager = forum_manager
        self.monitor = monitor
        self.local_data_path = local_data_path
        self.src_mode = src_mode
        self._cancelled = False

        agent_config = config.get("agent_llm", {})
        self.collect_agent = CollectAgent("CollectAgent", agent_config.get("collect_agent", {}), forum_manager)
        self.sentiment_agent = SentimentAgent("SentimentAgent", agent_config.get("sentiment_agent", {}), forum_manager)
        self.trend_agent = TrendAgent("TrendAgent", agent_config.get("trend_agent", {}), forum_manager)
        self.report_agent = ReportAgent("ReportAgent", agent_config.get("report_agent", {}), forum_manager)

    def cancel(self):
        """Signal the pipeline to stop at the next checkpoint."""
        self._cancelled = True

    # ── Blocking mode (script / headless usage) ────────────────────

    def run_pipeline(self) -> Dict[str, Any]:
        """Blocking call returning final result dict."""
        result = {"status": "error", "message": "pipeline did not produce output"}

        for event in self.stream_pipeline():
            if isinstance(event, ReportEvent):
                result = {"status": "success", "data": {"report_data": {
                    "keyword": event.keyword,
                    "sentiment_summary": event.sentiment_summary,
                    "trend_summary": event.trend_summary,
                    "analyzed_news": event.analyzed_news,
                    "nodes": event.nodes,
                    "edges": event.edges,
                    "ai_insights": event.ai_insights,
                    "graph_insights": event.graph_insights,
                    "collect_meta": event.collect_meta,
                    "forum_debate": event.forum_debate,
                }}}
            if self._cancelled:
                break

        return result

    # ── Generator mode (TUI / headless) ────────────────────────────

    def stream_pipeline(self) -> Generator[Union[PipelineEvent, ForumEvent, ReportEvent, ErrorEvent], None, None]:
        """Main pipeline as a generator. Yields events for the TUI to consume."""

        self.forum_manager.write("SYSTEM", 1, f"任务启动：开始分析 '{self.keyword}'")

        # ── 阶段 1: 数据收集 ──
        if self._cancelled:
            return
        yield PipelineEvent(type="agent_start", agent="CollectAgent", progress=5)

        collect_input = {"keyword": self.keyword, "src_mode": self.src_mode}
        if self.local_data_path:
            collect_input["local_data_path"] = self.local_data_path
            self.forum_manager.write("SYSTEM", 1, f"检测到本地数据路径: {self.local_data_path}")

        collect_res = self.collect_agent.run(collect_input)
        if collect_res["status"] == "error":
            self.forum_manager.write("SYSTEM", 1, "数据收集失败，任务终止")
            yield PipelineEvent(type="agent_error", agent="CollectAgent", progress=30,
                                message="数据收集失败")
            yield ErrorEvent(stage="collect", message="数据收集失败", fatal=True)
            return

        news_data = collect_res["data"]["news"]
        collect_meta = collect_res["data"].get("collect_meta", {})
        yield PipelineEvent(type="agent_done", agent="CollectAgent", progress=30,
                            data={"news_count": len(news_data), "meta": collect_meta})

        # ── 阶段 2: 情感分析 ──
        if self._cancelled:
            return
        yield PipelineEvent(type="agent_start", agent="SentimentAgent", progress=35)

        sent_res = self.sentiment_agent.run({"news": news_data})
        if sent_res["status"] == "error":
            self.forum_manager.write("SYSTEM", 1, "情感分析失败，任务终止")
            yield PipelineEvent(type="agent_error", agent="SentimentAgent", progress=52,
                                message="情感分析失败")
            yield ErrorEvent(stage="sentiment", message="情感分析失败", fatal=True)
            return

        yield PipelineEvent(type="agent_done", agent="SentimentAgent", progress=52)

        # ── 阶段 3: 趋势预测 ──
        if self._cancelled:
            return
        yield PipelineEvent(type="agent_start", agent="TrendAgent", progress=55)

        trend_res = self.trend_agent.run({
            "analyzed_news": sent_res["data"]["analyzed_news"],
            "collect_meta": collect_meta
        })
        if trend_res.get("status") == "error":
            yield ErrorEvent(stage="trend", message=trend_res.get("summary", "趋势预测异常"))
            trend_res.setdefault("data", {})
            trend_res["data"].setdefault("trend_summary", {
                "trend_direction": "unknown",
                "confidence": 0.0,
                "data_quality": "预测失败",
                "data_note": f"趋势预测异常: {trend_res.get('summary', '未知错误')}",
                "forecast_window": 0,
            })
            trend_res["data"].setdefault("trend_results", {"predictions": []})
        yield PipelineEvent(type="agent_done", agent="TrendAgent", progress=66)

        # ── 等待 Monitor 触发 Host 总结 ──
        self.forum_manager.write("SYSTEM", 1, "等待论坛主持人 (Host) 综合研判...")
        if hasattr(self.monitor, "wait_for_host_guidance"):
            host_msg = self.monitor.wait_for_host_guidance(timeout=cfg.forum_wait_timeout())
        else:
            time.sleep(3)
            host_msg = self.forum_manager.get_latest_host_guidance()

        # ── 阶段 4: 第二轮迭代 (如有 Host 反馈) ──
        skip_markers = ("Error", "HOST错误", "HOST提示", "LLM不可用", "API鉴权")
        if host_msg and not any(m in host_msg for m in skip_markers):
            yield ForumEvent(speaker="HOST", round_num=1, content=host_msg)
            supplement_max = cfg.host_research_max()
            if supplement_max > 0:
                self.collect_agent.iteration_count = 2
                supplement_res = self.collect_agent.run({
                    "keyword": self.keyword,
                    "src_mode": self.src_mode,
                    "max_results": supplement_max,
                    "feedback": host_msg,
                })
                if supplement_res.get("status") == "success":
                    news_data = self._merge_news(
                        news_data,
                        supplement_res.get("data", {}).get("news", [])
                    )
                    supplement_meta = supplement_res.get("data", {}).get("collect_meta", {})
                    collect_meta["total_count"] = len(news_data)
                    collect_meta["source_count"] = len(set(n.get("source", "") for n in news_data))
                    collect_meta.setdefault("sources", [])
                    collect_meta["sources"].extend(supplement_meta.get("sources", []))
                    self.forum_manager.write(
                        "SYSTEM", 2,
                        f"已根据 Host 盲区补充采集，合并后共 {len(news_data)} 条。"
                    )

            self.sentiment_agent.iteration_count = 2
            self.trend_agent.iteration_count = 2
            sent_res2 = self.sentiment_agent.run({"news": news_data, "feedback": host_msg})
            if sent_res2.get("status") != "error":
                sent_res = sent_res2

            trend_res2 = self.trend_agent.run({
                "analyzed_news": sent_res["data"].get("analyzed_news", []),
                "feedback": host_msg,
                "collect_meta": collect_meta
            })
            if trend_res2.get("status") == "error":
                trend_res2.setdefault("data", {})
                trend_res2["data"].setdefault("trend_summary", {
                    "trend_direction": "unknown", "confidence": 0.0,
                    "data_quality": "预测失败",
                    "data_note": f"趋势预测异常: {trend_res2.get('summary', '未知错误')}",
                    "forecast_window": 0,
                })
                trend_res2["data"].setdefault("trend_results", {"predictions": []})
            trend_res = trend_res2

        # ── 阶段 5: 报告生成 ──
        if self._cancelled:
            return
        yield PipelineEvent(type="agent_start", agent="ReportAgent", progress=85)

        sentiment_summary = sent_res["data"].get("summary", {})
        trend_summary = trend_res["data"].get("trend_summary", {})

        report_res = self.report_agent.run({
            "task_id": self.task_id,
            "keyword": self.keyword,
            "sentiment_summary": sentiment_summary,
            "trend_summary": trend_summary,
            "analyzed_news": sent_res["data"].get("analyzed_news", []),
            "trend_results": trend_res["data"].get("trend_results", {}),
            "forum_log": self.forum_manager.read_all_lines()
        })

        # 事件图谱生成
        nodes, edges = [], []
        graph_insights = {}
        try:
            from ..analysis.event_extractor import EventExtractor
            extractor = EventExtractor()
            events_data = extractor.extract_events(sent_res["data"].get("analyzed_news", []))
            nodes = events_data.get("nodes", [])
            edges = events_data.get("edges", [])

            from ..knowledge.graph_insights import analyze_graph
            graph_insights = analyze_graph(nodes, edges)
        except Exception as e:
            self.forum_manager.write("SYSTEM", 1, f"事件提取异常：{str(e)}")

        # Generate causal chain text for terminal display
        causal_chains = []
        try:
            from ..visualization.causal_chain import format_causal_chains
            causal_chains = format_causal_chains(nodes, edges, top_k=5)
        except Exception:
            pass

        # Generate standalone graph HTML
        graph_html_path = ""
        try:
            from ..visualization.graph_renderer import render_graph_html
            graph_html_path = render_graph_html(
                nodes=nodes, edges=edges,
                keyword=self.keyword, task_id=self.task_id,
                output_dir=f"{cfg.results_dir()}/reports"
            )
        except Exception as e:
            self.forum_manager.write("SYSTEM", 1, f"图谱渲染异常：{str(e)}")

        # Knowledge store persistence
        try:
            from ..knowledge.event_store import EventStore
            store = EventStore(cfg.knowledge_db_path())
            store.save_task_events(
                task_id=self.task_id,
                keyword=self.keyword,
                analyzed_news=sent_res["data"].get("analyzed_news", []),
            )
        except Exception as e:
            self.forum_manager.write("SYSTEM", 1, f"事件知识库写入异常：{str(e)}")

        # Generate HTML report file (backward compat)
        try:
            from ..report.export_html import export_html_report
            report_data = report_res.get("data", {}).get("report_data", {})
            output_path = f"{cfg.results_dir()}/reports/{self.task_id}.html"
            export_html_report(report_data, output_path)
        except Exception:
            pass

        yield PipelineEvent(type="agent_done", agent="ReportAgent", progress=100)

        # Extract forum debate and AI insights from report
        report_data = report_res.get("data", {}).get("report_data", {})
        ai_insights = report_data.get("ai_insights", {})

        self.forum_manager.write("SYSTEM", 2, "分析任务全面完成。")

        yield ReportEvent(
            task_id=self.task_id,
            keyword=self.keyword,
            conclusion=report_res.get("summary", ""),
            sentiment_summary=sentiment_summary,
            trend_summary=trend_summary,
            nodes=nodes,
            edges=edges,
            ai_insights=ai_insights,
            graph_insights=graph_insights,
            causal_chains=causal_chains,
            graph_html_path=graph_html_path,
            forum_debate=report_data.get("forum_debate", []),
            analyzed_news=sent_res["data"].get("analyzed_news", []),
            collect_meta=collect_meta,
        )

    @staticmethod
    def _merge_news(primary: list, supplement: list) -> list:
        merged = list(primary or [])
        seen = set()
        for item in merged:
            key = item.get("url") or item.get("link") or item.get("title", "")[:80]
            if key:
                seen.add(key)
        for item in supplement or []:
            key = item.get("url") or item.get("link") or item.get("title", "")[:80]
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            merged.append(item)
        return merged
