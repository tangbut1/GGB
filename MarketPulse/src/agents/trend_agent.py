from typing import Dict, Any
from .base_agent import BaseAgent
from ..analysis.trend_prediction import TrendPredictor
from ..analysis.sentiment_indicators import compute_indicators

class TrendAgent(BaseAgent):
    def _get_system_prompt(self) -> str:
        return (
            "你现在的角色是【蓝方-理性看多/对冲策略师(Blue Team / TrendAgent)】。\n"
            "结合时序模型的预测方向和论坛中他人的意见，给出理性的趋势预测。\n"
            "作为蓝方，你必须在【危机分析师(红方)】的悲观情绪中寻找破局点，寻找历史基线、事件反转点和长尾商业机会。\n"
            "如果这是多轮对抗，请务必针对红方提出的恐慌进行坚决反驳！"
        )

    def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        analyzed_news = input_data.get("analyzed_news", [])
        feedback = input_data.get("feedback", "")
        collect_meta = input_data.get("collect_meta", {})

        if not analyzed_news:
             return {"status": "error", "agent": self.name, "data": {}, "summary": "缺少情感分析数据"}

        total_count = len(analyzed_news)
        date_range = collect_meta.get("date_range", "未知")
        source_count = collect_meta.get("source_count", "未知")

        # 数据质量评级
        if total_count >= 500:
            data_quality = "高"
            data_note = "数据量充足，趋势判断可靠，可用于决策参考。"
        elif total_count >= 200:
            data_quality = "中"
            data_note = "数据量适中，趋势方向可信，但细节波动可能不够精确。"
        else:
            data_quality = "低"
            data_note = "数据量偏少，趋势仅供方向性参考，不建议作为唯一决策依据。"

        predictor = TrendPredictor()
        # 动态调整预测窗口：数据跨度越大，预测越远
        predictor.forecast_periods = 30 if total_count >= 200 else 14 if total_count >= 100 else 7
        trend_results = predictor.analyze_market_sentiment_trend(analyzed_news)
        trend_summary = predictor.get_trend_summary(trend_results)

        direction = trend_summary.get("trend_direction", "neutral")
        confidence = trend_summary.get("confidence", 0.0)
        # 置信度随数据量调整
        if total_count < 100:
            confidence = min(confidence, 0.4)
        elif total_count < 300:
            confidence = min(confidence, 0.7)

        predictions_count = len(trend_results.get("predictions", []))
        forecast_window = predictor.forecast_periods

        llm_prompt = (
            f"趋势分析任务（蓝方视角）：\n"
            f"【数据概况】共 {total_count} 条数据，时间跨度 {date_range}，"
            f"来自 {source_count} 个数据源。数据质量评级：{data_quality}。{data_note}\n"
            f"【模型结果】方向={direction}，置信度={confidence:.1%}，"
            f"预测窗口={forecast_window}天，预测点={predictions_count}个。\n"
        )
        if feedback:
            llm_prompt += f"【主持人指引及红方观点】{feedback}\n"
        # 跨会话项目记忆：与 sentiment_agent 同一约定，作为背景而非指令，
        # 历史结论与本次数据冲突时以本次为准。
        memory_context = input_data.get("memory_context")
        if memory_context:
            llm_prompt += f"\n{memory_context}\n"
        llm_prompt += (
            "请按以下结构输出你的理性对冲分析：\n"
            "1. 【蓝方立论】情绪噪音剥离（指出当前市场的过度恐慌或不合理之处）\n"
            "2. 【反转信号】（寻找可能扭转局面的政策、补偿措施或历史基线数据支撑）\n"
            "3. 【长尾机会】（别人恐惧我贪婪，推演反弹窗口与潜在的商业机会）"
        )

        insight = self.call_llm(llm_prompt)
        degraded = self.llm_unavailable(insight)

        # LLM 不可用时不能沉默：蓝方失声会让裁判只听到红方一面之词，
        # 辩论退化成单方陈述。用本地时序模型的结果合成蓝方立论。
        if degraded:
            direction_text = {
                "positive": "积极上行", "negative": "消极下行", "neutral": "震荡持平",
            }.get(direction, direction)
            lines = [
                f"【蓝方立论】本地趋势模型结论：情绪走向{direction_text}，"
                f"模型置信度 {confidence:.0%}，预测窗口 {forecast_window} 天，"
                f"有效预测点 {predictions_count} 个。",
                f"【数据底座】共 {total_count} 条数据、{source_count} 个来源，"
                f"时间跨度 {date_range}，数据质量评级：{data_quality}。",
                f"【理性判断】红方的恐慌需要与历史基线对照："
                f"{trend_summary.get('recommendation', '建议保持观望')}。",
            ]

            # 第二轮必须点名回应红方，否则两轮立论一字不差，辩论名不副实。
            # limit 直接按展示长度给：引文超长时 extract_opponent_claim 会
            # 按句末截断，这里再切一次就会把词断在半中间。
            opponent = self.extract_opponent_claim(feedback, limit=90)
            if opponent:
                lines.append(
                    f"【驳斥红方】红方以负面样本的绝对数量立论，但趋势模型看的是走向而非存量："
                    f"在 {forecast_window} 天预测窗口内情绪走向为{direction_text}、"
                    f"置信度 {confidence:.0%}。对方引用的“{opponent}”"
                    "把历史存量当成未来风险，属于用后视镜开车。"
                )

            lines.append("（裁判 LLM 暂不可用，本立论由本地模型生成）")
            insight = "\n".join(lines)
        self.write_to_forum_log(insight)

        # 注入增强后的元信息
        trend_summary["data_quality"] = data_quality
        trend_summary["data_note"] = data_note
        trend_summary["forecast_window"] = forecast_window
        # 模型类型与观测点数要能透传到前端的方法论说明里：Prophet 失败时
        # 后端会自动降级成线性回归基线，两者的置信区间含义完全不同
        # （Prophet 是不确定性区间，基线是残差 ±1.96σ），界面必须说清楚
        # 用的是哪一个，否则用户会把基线的区间当成 Prophet 的不确定性。
        trend_summary.setdefault("model_type", "unknown")
        trend_summary.setdefault("data_points", total_count)
        # Prophet 拟合失败时把真实原因带出去。后端降级到线性基线本身是
        # 设计内的兜底，但"为什么降级"必须可查——否则用户看着趋势图
        # 无从判断该修环境还是该接受这个精度。
        if trend_summary.get("model_type") == "baseline":
            trend_summary["fallback_reason"] = predictor.fit_error or "未知原因"
        else:
            trend_summary["fallback_reason"] = ""

        # 多维指标：单条情绪指数无法评价一次舆情（同样的均值可能来自
        # "少量极端负面"或"温和全面偏负"）。全部由本批已打分样本算出，
        # 不引入任何外部基准或插值。
        indicators = compute_indicators(analyzed_news)
        trend_summary["indicators"] = indicators
        # 时序预测的最低门槛：至少 2 个有日期的不同日期。少于这个数时
        # "未来 30 天"没有任何依据，前端要说明是横截面快照而不是预测。
        trend_summary["forecast_feasible"] = indicators["sample"]["known_days"] >= 2

        return {
            "status": "success",
            "agent": self.name,
            "data": {
                "trend_results": trend_results,
                "trend_summary": trend_summary,
                "collect_meta": collect_meta,
            },
            "summary": (
                f"趋势预测完成，方向 {direction}（数据质量: {data_quality}）"
                if degraded else insight
            )
        }

