from typing import Dict, Any
from .base_agent import BaseAgent
from .. import config as cfg
from ..analysis.trend_prediction import TrendPredictor

class TrendAgent(BaseAgent):
    def _get_system_prompt(self) -> str:
        return (
            "你是一名具备【定性因果推断】能力的顶级趋势分析AI(TrendAgent)。"
            "如果基础时序模型因为数据量少（如仅有单日数据）而给出低置信度的判断，"
            "你必须立即放弃死板的曲线外推，改用因果逻辑进行深度推演："
            "识别事件的【触发因子 -> 核心争议点 -> 传播裂变层 -> 可能的次生危机】，"
            "并结合历史同类事件规律，给出前瞻性的走势推判。"
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
        base_periods = cfg.analysis_forecast_periods()
        if total_count >= 200:
            predictor.forecast_periods = base_periods
        elif total_count >= 100:
            predictor.forecast_periods = max(7, base_periods // 2)
        else:
            predictor.forecast_periods = max(5, base_periods // 4)
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
            f"趋势分析任务：\n"
            f"【数据概况】共 {total_count} 条数据，时间跨度 {date_range}，"
            f"来自 {source_count} 个数据源。数据质量评级：{data_quality}。{data_note}\n"
            f"【模型结果】方向={direction}，置信度={confidence:.1%}，"
            f"预测窗口={forecast_window}天，预测点={predictions_count}个。\n"
        )
        if feedback:
            llm_prompt += f"【主持人指引】{feedback}\n"
        llm_prompt += (
            "请按以下结构输出你的科学趋势分析：\n"
            "1. 因果推断综述（分析事件链条：触发点->当前态势->下一个可能的引爆点）\n"
            "2. 关键发现（跳出数字表象，指出核心情绪驱动力与异常线索）\n"
            "3. 后市沙盘推演（无论数据多少，基于事理逻辑，推演未来3-7天的2种可能走向及应对策略）"
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

