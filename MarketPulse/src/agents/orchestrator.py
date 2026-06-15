import time
from typing import Dict, Any, Optional
from flask_socketio import SocketIO
from .collect_agent import CollectAgent
from .sentiment_agent import SentimentAgent
from .trend_agent import TrendAgent
from .report_agent import ReportAgent


class OrchestratorAgent:
    """协调各 Agent 执行分析流水线，支持论坛协作模式"""

    def __init__(self, task_id: str, keyword: str, config: dict,
                 forum_manager, monitor,
                 socketio: Optional[SocketIO] = None,
                 local_data_path: Optional[str] = None,
                 src_mode: str = "news"):
        self.task_id = task_id
        self.keyword = keyword
        self.config = config
        self.forum_manager = forum_manager
        self.monitor = monitor
        self.socketio = socketio
        self.local_data_path = local_data_path
        self.src_mode = src_mode

        agent_config = config.get("agent_llm", {})
        self.collect_agent = CollectAgent("CollectAgent", agent_config.get("collect_agent", {}), forum_manager)
        self.sentiment_agent = SentimentAgent("SentimentAgent", agent_config.get("sentiment_agent", {}), forum_manager)
        self.trend_agent = TrendAgent("TrendAgent", agent_config.get("trend_agent", {}), forum_manager)
        self.report_agent = ReportAgent("ReportAgent", agent_config.get("report_agent", {}), forum_manager)

    def _emit(self, event: str, data: dict):
        """安全地向对应 task_id 房间推送 SocketIO 事件"""
        if self.socketio:
            try:
                self.socketio.emit(event, data, room=self.task_id)
            except Exception:
                pass

    def run_pipeline(self) -> Dict[str, Any]:
        self.forum_manager.write("SYSTEM", 1, f"任务启动：开始分析 '{self.keyword}'")

        error_log = []

        # ── 阶段 1: 数据收集 ──
        self._emit("agent_update", {"agent": "CollectAgent", "status": "active", "progress": 5})
        collect_input = {"keyword": self.keyword, "src_mode": self.src_mode}
        if self.local_data_path:
            collect_input["local_data_path"] = self.local_data_path
            self.forum_manager.write("SYSTEM", 1, f"检测到本地数据路径: {self.local_data_path}")

        collect_res = self.collect_agent.run(collect_input)
        if collect_res["status"] == "error":
            error_log.append(f"CollectAgent: {collect_res.get('summary', '未知错误')}")
            self.forum_manager.write("SYSTEM", 1, "数据收集失败，任务终止")
            self._emit("agent_update", {"agent": "CollectAgent", "status": "err", "progress": 30})
            self._emit("error", {"stage": "collect", "message": "数据收集失败"})
            return {"status": "error", "message": "数据收集失败"}

        news_data = collect_res["data"]["news"]
        collect_meta = collect_res["data"].get("collect_meta", {})
        self._emit("agent_update", {"agent": "CollectAgent", "status": "done", "progress": 30})

        # ── 阶段 2: 情感分析 ──
        self._emit("agent_update", {"agent": "SentimentAgent", "status": "active", "progress": 35})
        sent_res = self.sentiment_agent.run({"news": news_data})
        if sent_res["status"] == "error":
            error_log.append(f"SentimentAgent: {sent_res.get('summary', '未知错误')}")
            self.forum_manager.write("SYSTEM", 1, "情感分析失败，任务终止")
            self._emit("agent_update", {"agent": "SentimentAgent", "status": "err", "progress": 52})
            self._emit("error", {"stage": "sentiment", "message": "情感分析失败"})
            return {"status": "error", "message": "情感分析失败"}

        self._emit("agent_update", {"agent": "SentimentAgent", "status": "done", "progress": 52})

        # ── 阶段 3: 趋势预测 ──
        self._emit("agent_update", {"agent": "TrendAgent", "status": "active", "progress": 55})
        trend_res = self.trend_agent.run({
            "analyzed_news": sent_res["data"]["analyzed_news"],
            "collect_meta": collect_meta
        })
        if trend_res.get("status") == "error":
            error_log.append(f"TrendAgent: {trend_res.get('summary', '趋势预测异常')}")
            self._emit("error", {"stage": "trend", "message": trend_res.get('summary', '趋势预测异常')})
            # 趋势预测失败不终止，注入降级趋势摘要防止下游拿到空 dict
            trend_res.setdefault("data", {})
            trend_res["data"].setdefault("trend_summary", {
                "trend_direction": "unknown",
                "confidence": 0.0,
                "data_quality": "预测失败",
                "data_note": f"趋势预测异常: {trend_res.get('summary', '未知错误')}",
                "forecast_window": 0,
            })
            trend_res["data"].setdefault("trend_results", {"predictions": []})
        self._emit("agent_update", {"agent": "TrendAgent", "status": "done", "progress": 66})

        # ── 等待 Monitor 触发 Host 总结 ──
        self.forum_manager.write("SYSTEM", 1, "等待论坛主持人 (Host) 综合研判...")
        time.sleep(3)

        # ── 阶段 4: 第二轮迭代 (如有 Host 反馈) ──
        host_msg = self.forum_manager.get_latest_host_guidance()
        if host_msg and "Error" not in host_msg and "HOST错误" not in host_msg:
            self._emit("forum_message", {"type": "HOST", "content": host_msg})
            self.sentiment_agent.iteration_count = 2
            self.trend_agent.iteration_count = 2
            sent_res = self.sentiment_agent.run({"news": news_data, "feedback": host_msg})
            trend_res = self.trend_agent.run({
                "analyzed_news": sent_res["data"]["analyzed_news"],
                "feedback": host_msg,
                "collect_meta": collect_meta
            })

        self._emit("agent_update", {"agent": "SentimentAgent", "status": "done", "progress": 80})
        self._emit("agent_update", {"agent": "TrendAgent", "status": "done", "progress": 80})

        # ── 阶段 5: 报告生成 ──
        self._emit("agent_update", {"agent": "ReportAgent", "status": "active", "progress": 85})
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

        # Event graph generation has been removed as per user request
        if "data" in report_res and "report_data" in report_res["data"]:
            report_res["data"]["report_data"]["nodes"] = []
            report_res["data"]["report_data"]["edges"] = []
            report_res["data"]["report_data"]["collect_meta"] = collect_meta

        # 生成 HTML 报告文件
        from ..report.export_html import export_html_report
        report_data = report_res.get("data", {}).get("report_data", {})
        results_dir = self.config.get("data", {}).get("results_dir", "results")
        output_path = f"{results_dir}/reports/{self.task_id}.html"
        export_html_report(report_data, output_path)

        self._emit("agent_update", {"agent": "ReportAgent", "status": "done", "progress": 100})
        self._emit("report_ready", {"task_id": self.task_id, "url": f"/report/{self.task_id}"})

        self.forum_manager.write("SYSTEM", 2, "分析任务全面完成。")
        return report_res
