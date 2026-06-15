from typing import Dict, Any
from .base_agent import BaseAgent
from ..analysis.trend_prediction import TrendPredictor

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
        llm_prompt += (
            "请按以下结构输出你的理性对冲分析：\n"
            "1. 【蓝方立论】情绪噪音剥离（指出当前市场的过度恐慌或不合理之处）\n"
            "2. 【反转信号】（寻找可能扭转局面的政策、补偿措施或历史基线数据支撑）\n"
            "3. 【长尾机会】（别人恐惧我贪婪，推演反弹窗口与潜在的商业机会）"
        )

        insight = self.call_llm(llm_prompt)

        if insight and "Error" not in insight:
            self.write_to_forum_log(insight)

        # 注入增强后的元信息
        trend_summary["data_quality"] = data_quality
        trend_summary["data_note"] = data_note
        trend_summary["forecast_window"] = forecast_window

        return {
            "status": "success",
            "agent": self.name,
            "data": {
                "trend_results": trend_results,
                "trend_summary": trend_summary,
                "collect_meta": collect_meta,
            },
            "summary": insight if ("Error" not in insight and insight) else f"趋势预测完成，方向 {direction}（数据质量: {data_quality}）"
        }

