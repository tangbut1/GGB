"""Red-Blue multi-agent debate pipeline.

Flow:
    Collect (data)
      → Round 1:  Red (SentimentAgent, crisis analyst) opening statement
                  Blue (TrendAgent, rational analyst) opening statement
      → Judge guidance (Host points out the core disagreement)
      → Round 2:  Red rebuttal  (attacks Blue's opening)
                  Blue rebuttal (attacks Red's rebuttal)
      → Judge verdict (structured final ruling)
      → Report (ReportAgent compiles everything)

``stream_pipeline()`` yields events (see ``src/events.py``); ``run_pipeline()``
consumes them and keeps the legacy blocking return contract for the Flask
layer, translating events into SocketIO emissions.
"""

import time
from typing import Dict, Any, Optional

from flask_socketio import SocketIO

from .collect_agent import CollectAgent
from .sentiment_agent import SentimentAgent
from .trend_agent import TrendAgent
from .report_agent import ReportAgent
from ..events import PipelineEvent, ForumEvent, ReportEvent, ErrorEvent
from ..forum.llm_host import LLMHost

# 辩论角色映射：前端按 role 渲染红/蓝/裁判卡片
ROLE_MAP = {
    "CollectAgent": "collect",
    "SentimentAgent": "red",
    "TrendAgent": "blue",
    "ReportAgent": "report",
    "HOST": "judge",
}

# role → 卡片标题。必须和前端 CenterWorkspace 的 ROLE_STYLES[role].label
# 逐字一致：实时观看时前端拿不到 label（_to_debate_turn 不下发），用自己
# 的兜底文案；历史回放时后端下发 label。两边不一致的话，同一场辩论在直播时
# 显示"红方 · 危机分析师"，点左侧历史记录却变成"危机分析 (Red Team)"，
# 读者会以为两次不是同一批人说的话。
TURN_LABELS = {
    "red": "红方 · 危机分析师",
    "blue": "蓝方 · 理性分析师",
    "collect": "采集 Agent",
    "report": "报告 Agent",
    "judge": "裁判终裁",
    "agent": "分析 Agent",
}


class OrchestratorAgent:
    """协调各 Agent 执行红蓝辩论分析流水线"""

    def __init__(self, task_id: str, keyword: str, config: dict,
                 forum_manager, monitor,
                 socketio: Optional[SocketIO] = None,
                 local_data_path: Optional[str] = None,
                 src_mode: str = "news",
                 memory_context: str = ""):
        self.task_id = task_id
        self.keyword = keyword
        self.config = config
        self.forum_manager = forum_manager
        self.monitor = monitor
        self.socketio = socketio
        self.local_data_path = local_data_path
        self.src_mode = src_mode
        # 同一主题下此前分析的结论（跨会话项目记忆）。空串表示这个主题
        # 是首次分析，各 Agent 照常只依据本次采集的数据发言。
        self.memory_context = memory_context or ""

        agent_config = config.get("agent_llm", {})
        self.collect_agent = CollectAgent("CollectAgent", agent_config.get("collect_agent", {}), forum_manager)
        self.sentiment_agent = SentimentAgent("SentimentAgent", agent_config.get("sentiment_agent", {}), forum_manager)
        self.trend_agent = TrendAgent("TrendAgent", agent_config.get("trend_agent", {}), forum_manager)
        self.report_agent = ReportAgent("ReportAgent", agent_config.get("report_agent", {}), forum_manager)
        self.host = LLMHost(agent_config.get("forum_host", {}))

        # 辩论状态（run_pipeline / stream_pipeline 共享）
        self.debate = {
            "red_round1": "", "blue_round1": "",
            "red_round2": "", "blue_round2": "",
            "guidance": "", "verdict": {},
        }

        # 追问轮次计数。用户的追问是新一轮辩论，round 从 3 起算，和前面两轮
        # 连起来，前端卡片上显示的"第 N 轮"才是一条完整的时间线。
        self.followup_round = 2
        # 追问要用到首轮采集的原始数据。stream_pipeline 里它们是局部变量，
        # 存成实例属性，否则追问时只能拿到结论拿不到论据。
        self.news_data: list = []
        self.analyzed_news: list = []
        self.collect_meta: Dict[str, Any] = {}

    # ── socket helpers ───────────────────────────────────────────────
    def _emit(self, event: str, data: dict):
        if self.socketio:
            try:
                self.socketio.emit(event, data, room=self.task_id)
            except Exception:
                pass

    def _latest_speech(self, agent_name: str) -> str:
        """取某 Agent 最近一次写入论坛的发言内容。"""
        try:
            msgs = self.forum_manager.get_all_messages()
        except Exception:
            return ""
        for msg in reversed(msgs):
            if msg.get("agent") == agent_name:
                return msg.get("content", "")
        return ""

    # ── 事件生成核心 ─────────────────────────────────────────────────
    def stream_pipeline(self):
        """Yield PipelineEvent / ForumEvent / ReportEvent / ErrorEvent."""
        self.forum_manager.write("SYSTEM", 1, f"任务启动：开始分析 '{self.keyword}'（红蓝辩论模式）")

        # ── 阶段 1: 数据收集 ──
        yield PipelineEvent(stage="collect", agent="CollectAgent",
                            status="active", progress=5, role="collect",
                            message="多源采集中...")
        collect_input = {"keyword": self.keyword, "src_mode": self.src_mode}
        if self.local_data_path:
            collect_input["local_data_path"] = self.local_data_path
            self.forum_manager.write("SYSTEM", 1, f"检测到本地数据路径: {self.local_data_path}")

        collect_res = self.collect_agent.run(collect_input)
        if collect_res.get("status") == "error":
            msg = collect_res.get("summary", "数据收集失败")
            self.forum_manager.write("SYSTEM", 1, "数据收集失败，任务终止")
            yield PipelineEvent(stage="collect", agent="CollectAgent",
                                status="err", progress=30, role="collect", message=msg)
            yield ErrorEvent(stage="collect", message=msg, fatal=True)
            return

        news_data = collect_res["data"]["news"]
        collect_meta = collect_res["data"].get("collect_meta", {})
        # 追问轮要用：红方复辩时得重新过一遍同一批语料，不能只看结论
        self.news_data = news_data
        self.collect_meta = collect_meta
        collect_speech = self._latest_speech("CollectAgent")
        yield PipelineEvent(stage="collect", agent="CollectAgent",
                            status="done", progress=30, role="collect",
                            content=collect_speech,
                            message=collect_res.get("summary", ""))

        # ── Round 1 立论: 红方 (SentimentAgent) ──
        yield PipelineEvent(stage="sentiment", agent="SentimentAgent",
                            status="active", progress=35, role="red", round=1,
                            message="红方立论中...")
        self.sentiment_agent.iteration_count = 1
        sent_res = self.sentiment_agent.run({"news": news_data, "memory_context": self.memory_context})
        if sent_res.get("status") == "error":
            msg = sent_res.get("summary", "情感分析失败")
            self.forum_manager.write("SYSTEM", 1, "情感分析失败，任务终止")
            yield PipelineEvent(stage="sentiment", agent="SentimentAgent",
                                status="err", progress=52, role="red", round=1, message=msg)
            yield ErrorEvent(stage="sentiment", message=msg, fatal=True)
            return

        self.debate["red_round1"] = self._latest_speech("SentimentAgent")
        self.analyzed_news = sent_res["data"].get("analyzed_news", [])
        yield PipelineEvent(stage="sentiment", agent="SentimentAgent",
                            status="done", progress=52, role="red", round=1,
                            content=self.debate["red_round1"],
                            message=sent_res.get("summary", ""))

        # ── Round 1 立论: 蓝方 (TrendAgent) ──
        yield PipelineEvent(stage="trend", agent="TrendAgent",
                            status="active", progress=55, role="blue", round=1,
                            message="蓝方立论中...")
        self.trend_agent.iteration_count = 1
        trend_res = self.trend_agent.run({
            "analyzed_news": sent_res["data"]["analyzed_news"],
            "collect_meta": collect_meta,
            "memory_context": self.memory_context,
        })
        if trend_res.get("status") == "error":
            # 趋势预测失败不致命：注入降级摘要，保证下游有数据
            msg = trend_res.get("summary", "趋势预测异常")
            yield ErrorEvent(stage="trend", message=msg, fatal=False)
            trend_res.setdefault("data", {})
            trend_res["data"].setdefault("trend_summary", {
                "trend_direction": "unknown",
                "confidence": 0.0,
                "data_quality": "预测失败",
                "data_note": f"趋势预测异常: {msg}",
                "forecast_window": 0,
            })
            trend_res["data"].setdefault("trend_results", {"predictions": []})

        self.debate["blue_round1"] = self._latest_speech("TrendAgent")
        yield PipelineEvent(stage="trend", agent="TrendAgent",
                            status="done", progress=66, role="blue", round=1,
                            content=self.debate["blue_round1"],
                            message=trend_res.get("summary", ""))

        # ── 裁判引导: Host 指出核心分歧 ──
        yield PipelineEvent(stage="debate", agent="HOST", status="active",
                            progress=70, role="judge", round=1,
                            message="裁判梳理分歧中...")
        guidance = self.host.generate_guidance(self.forum_manager.get_all_messages())
        if guidance and "【HOST错误】" not in guidance:
            self.debate["guidance"] = guidance
            self.forum_manager.write("HOST", 1, guidance)
            yield ForumEvent(agent="HOST", role="judge", round=1,
                             content=guidance, kind="guidance")
        else:
            # 裁判不可用不终止辩论，Round 2 在无引导下进行
            self.forum_manager.write(
                "SYSTEM", 1, f"裁判引导不可用（{guidance[:80] or '空响应'}），Round 2 将无引导进行。")

        # ── Round 2 反驳: 红方抨击蓝方立论 ──
        red_feedback = self._build_rebuttal_feedback(
            guidance, opponent_label="蓝方", opponent_text=self.debate["blue_round1"])
        yield PipelineEvent(stage="sentiment", agent="SentimentAgent",
                            status="active", progress=74, role="red", round=2,
                            message="红方反驳中...")
        self.sentiment_agent.iteration_count = 2
        sent_res2 = self.sentiment_agent.run({
            "news": news_data,
            "feedback": red_feedback,
            "memory_context": self.memory_context,
        })
        if sent_res2.get("status") == "success":
            sent_res = sent_res2  # 以第二轮深入分析结果定稿
        self.debate["red_round2"] = self._latest_speech("SentimentAgent")
        yield PipelineEvent(stage="sentiment", agent="SentimentAgent",
                            status="done", progress=80, role="red", round=2,
                            content=self.debate["red_round2"],
                            message="红方反驳完成")

        # ── Round 2 反驳: 蓝方回击红方 ──
        blue_feedback = self._build_rebuttal_feedback(
            guidance, opponent_label="红方", opponent_text=self.debate["red_round2"])
        yield PipelineEvent(stage="trend", agent="TrendAgent",
                            status="active", progress=82, role="blue", round=2,
                            message="蓝方反驳中...")
        self.trend_agent.iteration_count = 2
        trend_res2 = self.trend_agent.run({
            "analyzed_news": sent_res["data"]["analyzed_news"],
            "feedback": blue_feedback,
            "collect_meta": collect_meta,
            "memory_context": self.memory_context,
        })
        if trend_res2.get("status") == "success":
            trend_res = trend_res2
        self.debate["blue_round2"] = self._latest_speech("TrendAgent")
        yield PipelineEvent(stage="trend", agent="TrendAgent",
                            status="done", progress=85, role="blue", round=2,
                            content=self.debate["blue_round2"],
                            message="蓝方反驳完成")

        # ── 终裁: Judge 结构化裁定 ──
        yield PipelineEvent(stage="debate", agent="HOST", status="active",
                            progress=88, role="judge", round=2,
                            message="裁判终裁中...")
        verdict = self.host.render_verdict(
            keyword=self.keyword,
            red_text="\n\n".join(filter(None, [self.debate["red_round1"], self.debate["red_round2"]])),
            blue_text="\n\n".join(filter(None, [self.debate["blue_round1"], self.debate["blue_round2"]])),
            guidance=self.debate["guidance"],
        )
        self.debate["verdict"] = verdict
        verdict_text = self._format_verdict_text(verdict)
        # 终裁文本随 debate 存档：客户端断线重连后，app.py 的 join 回放
        # 需要用它补发 forum_message，否则终裁在轮询切换瞬间丢失。
        self.debate["verdict_text"] = verdict_text
        self.forum_manager.write("HOST", 2, verdict_text)
        yield ForumEvent(agent="HOST", role="judge", round=2,
                         content=verdict_text, kind="verdict", verdict=verdict)

        # ── 阶段 5: 报告生成 ──
        yield PipelineEvent(stage="report", agent="ReportAgent",
                            status="active", progress=92, role="report",
                            message="汇总定稿中...")
        report_res = self.report_agent.run({
            "task_id": self.task_id,
            "keyword": self.keyword,
            "sentiment_summary": sent_res["data"].get("summary", {}),
            "trend_summary": trend_res["data"].get("trend_summary", {}),
            "analyzed_news": sent_res["data"].get("analyzed_news", []),
            "trend_results": trend_res["data"].get("trend_results", {}),
            "forum_messages": self.forum_manager.get_all_messages(),
            "verdict": verdict,
        })

        if report_res.get("status") == "error":
            msg = report_res.get("summary", "报告生成失败")
            yield PipelineEvent(stage="report", agent="ReportAgent",
                                status="err", progress=100, role="report", message=msg)
            yield ErrorEvent(stage="report", message=msg, fatal=True)
            return

        report_data = report_res.get("data", {}).get("report_data", {})
        report_data["collect_meta"] = collect_meta
        report_data["verdict"] = verdict

        # 生成 HTML 报告文件
        try:
            from ..report.export_html import export_html_report
            results_dir = self.config.get("data", {}).get("results_dir", "results")
            output_path = f"{results_dir}/reports/{self.task_id}.html"
            export_html_report(report_data, output_path)
        except Exception as e:
            self.forum_manager.write("SYSTEM", 1, f"HTML 报告导出失败: {e}")

        yield PipelineEvent(stage="report", agent="ReportAgent",
                            status="done", progress=100, role="report",
                            message=report_res.get("summary", ""))

        self.forum_manager.write("SYSTEM", 2, "分析任务全面完成。")
        yield ReportEvent(
            keyword=self.keyword,
            task_id=self.task_id,
            conclusion=report_res.get("summary", ""),
            sentiment_summary=report_data.get("sentiment_summary", {}),
            trend_summary=report_data.get("trend_summary", {}),
            verdict=verdict,
            report_data=report_data,
        )

    # ── helpers ──────────────────────────────────────────────────────
    def run_followup_debate(self, question: str) -> Dict[str, Any]:
        """围绕用户的追问再跑一轮红蓝辩论。

        与首轮的区别：不再采集数据（沿用首轮的语料），红蓝双方都拿到
        "用户追问 + 上一轮终裁 + 对方上一轮发言"三样东西，必须正面回应
        追问而不是重复立论。最后由裁判给出一个只针对这个追问的补充裁定。

        返回 {"status": "success", "turns": [...], "verdict": {...}}；
        任何一方失声都不算失败——用已有的发言继续，保证追问一定有回音。
        """
        question = (question or "").strip()
        if not question:
            return {"status": "error", "message": "追问内容为空"}
        if not self.news_data:
            return {"status": "error", "message": "首轮分析未采集到数据，无法追问"}

        self.followup_round += 1
        rnd = self.followup_round
        self.forum_manager.write("SYSTEM", rnd, f"用户追问：{question}")
        self._emit("agent_update", {"agent": "SentimentAgent", "status": "active",
                                    "progress": 74, "round": rnd})

        verdict = self.debate.get("verdict") or {}
        prior_verdict = (
            f"【上一轮终裁】立场 {verdict.get('stance', '未知')}，"
            f"置信度 {verdict.get('confidence', '未知')}。{verdict.get('summary', '')}"
            if verdict else ""
        )

        turns: list = []

        # ── 红方回应追问 ──
        self.sentiment_agent.iteration_count = rnd
        red_feedback = self._build_rebuttal_feedback(
            guidance=f"用户追问：{question}",
            opponent_label="蓝方",
            opponent_text=self.debate.get("blue_round2") or self.debate.get("blue_round1", ""),
        )
        if prior_verdict:
            red_feedback = f"{prior_verdict}\n\n{red_feedback}"
        red_res = self.sentiment_agent.run({"news": self.news_data, "feedback": red_feedback})
        red_text = self._latest_speech("SentimentAgent")
        if red_res.get("status") == "success" and red_text:
            self.debate["red_round2"] = red_text
            turn = {
                "author": "SentimentAgent", "role": "red", "round": rnd,
                "content": red_text,
            }
            turns.append(turn)
            # 显式推一次。后台日志广播器也会转到这条发言，前端按
            # (author, round, content) 去重，两路并发不会渲染出两张卡片。
            self._emit("debate_turn", {**turn, "type": "AGENT",
                                       "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")})
        else:
            self.forum_manager.write("SYSTEM", rnd, "红方本轮未发言（模型不可用或返回异常）")

        # ── 蓝方回应追问 ──
        self._emit("agent_update", {"agent": "TrendAgent", "status": "active",
                                    "progress": 82, "round": rnd})
        self.trend_agent.iteration_count = rnd
        blue_feedback = self._build_rebuttal_feedback(
            guidance=f"用户追问：{question}",
            opponent_label="红方",
            opponent_text=self.debate.get("red_round2") or self.debate.get("red_round1", ""),
        )
        if prior_verdict:
            blue_feedback = f"{prior_verdict}\n\n{blue_feedback}"
        blue_res = self.trend_agent.run({
            "analyzed_news": self.analyzed_news or self.news_data,
            "feedback": blue_feedback,
            "collect_meta": self.collect_meta,
        })
        blue_text = self._latest_speech("TrendAgent")
        if blue_res.get("status") == "success" and blue_text:
            self.debate["blue_round2"] = blue_text
            turn = {
                "author": "TrendAgent", "role": "blue", "round": rnd,
                "content": blue_text,
            }
            turns.append(turn)
            self._emit("debate_turn", {**turn, "type": "AGENT",
                                       "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")})
        else:
            self.forum_manager.write("SYSTEM", rnd, "蓝方本轮未发言（模型不可用或返回异常）")

        if not turns:
            return {
                "status": "error",
                "message": "红蓝双方本轮均未能发言，请检查 LLM 配置后重试",
            }

        # ── 裁判就追问给出补充裁定 ──
        self._emit("agent_update", {"agent": "HOST", "status": "active",
                                    "progress": 88, "round": rnd})
        # 只把本轮双方发言交给裁判：追问要的是"针对这个问题怎么看"，
        # 混进前两轮的全文会让裁定又变成一份泛泛的总结。
        red_this = next((t["content"] for t in turns if t["role"] == "red"), "")
        blue_this = next((t["content"] for t in turns if t["role"] == "blue"), "")
        new_verdict = self.host.render_verdict(
            keyword=self.keyword,
            red_text=red_this,
            blue_text=blue_this,
            guidance=f"用户追问：{question}",
        )
        self.debate["verdict"] = new_verdict
        verdict_text = self._format_verdict_text(new_verdict)
        self.debate["verdict_text"] = verdict_text
        self.forum_manager.write("HOST", rnd, verdict_text)
        judge_turn = {
            "author": "HOST", "role": "judge", "round": rnd,
            "content": verdict_text, "kind": "verdict", "verdict": new_verdict,
        }
        turns.append(judge_turn)
        self._emit("forum_message", judge_turn)
        self._emit("agent_update", {"agent": "HOST", "status": "done",
                                    "progress": 100, "round": rnd})

        return {"status": "success", "turns": turns, "verdict": new_verdict}

    @staticmethod
    def _build_rebuttal_feedback(guidance: str, opponent_label: str, opponent_text: str) -> str:
        parts = []
        if guidance:
            parts.append(f"【主持人指引】{guidance}")
        if opponent_text:
            parts.append(f"【{opponent_label}上一轮观点，请逐一驳斥】\n{opponent_text[:1200]}")
        parts.append("请输出你本轮的反驳发言，必须点名回应对方论据中的具体数据或逻辑。")
        return "\n\n".join(parts)

    @staticmethod
    def _format_verdict_text(verdict: dict) -> str:
        stance_cn = {"negative": "看空", "neutral": "中性", "positive": "看多"}
        lines = [
            "【终裁】",
            f"立场：{stance_cn.get(verdict.get('stance', 'neutral'), '中性')}"
            f"（置信度 {verdict.get('confidence', 0):.0%}）",
        ]
        if verdict.get("summary"):
            lines.append(f"裁定理由：{verdict['summary']}")
        if verdict.get("key_disagreements"):
            lines.append("核心分歧：" + "；".join(verdict["key_disagreements"]))
        if verdict.get("red_strongest"):
            lines.append(f"红方最有力论据：{verdict['red_strongest']}")
        if verdict.get("blue_strongest"):
            lines.append(f"蓝方最有力论据：{verdict['blue_strongest']}")
        if verdict.get("recommendation"):
            lines.append(f"行动建议：{verdict['recommendation']}")
        return "\n".join(lines)

    # ── 兼容包装：阻塞式执行 + SocketIO 推送 ─────────────────────────
    def run_pipeline(self) -> Dict[str, Any]:
        """Blocking wrapper around stream_pipeline().

        Translates events into SocketIO emissions and returns the final
        report dict (legacy contract used by app.py).

        发言（debate_turn）由 app.py 的后台日志广播器统一从论坛消息转发，
        这里只推送进度（agent_update）与裁判事件（forum_message），
        避免同一条发言被两个通道重复推送。
        """
        report_res: Dict[str, Any] = {"status": "error", "message": "管道未执行"}

        for event in self.stream_pipeline():
            if isinstance(event, PipelineEvent):
                self._emit("agent_update", {
                    "agent": event.agent,
                    "status": event.status,
                    "progress": event.progress,
                })
            elif isinstance(event, ForumEvent):
                payload = event.to_dict()
                payload["content"] = event.content
                self._emit("forum_message", payload)
            elif isinstance(event, ErrorEvent):
                if event.fatal:
                    self._emit("error", {"stage": event.stage, "message": event.message})
                    return {"status": "error", "message": event.message}
            elif isinstance(event, ReportEvent):
                report_res = {
                    "status": "success",
                    "agent": "ReportAgent",
                    "data": {"report_data": event.report_data},
                    "summary": event.conclusion,
                }

        return report_res
