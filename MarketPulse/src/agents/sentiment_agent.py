import json
import re
from typing import Dict, Any
from .base_agent import BaseAgent
from ..analysis.sentiment_analysis import SentimentAnalyzer

class SentimentAgent(BaseAgent):
    def _get_system_prompt(self) -> str:
        return (
            "你是一个金融情感分析师(SentimentAgent)。"
            "你会收到基础的情绪打分结果和新闻样本，你需要进行深度定性解读，"
            "并输出结构化的情感分布校正结果。"
            "SnowNLP 等自动化工具对财经/政治类中文文本有严重正向偏置，"
            "你的任务是校正这个偏差，给出真实的情感分布。"
        )

    def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        news_data = input_data.get("news", [])
        feedback = input_data.get("feedback", "")

        if not news_data:
            return {"status": "error", "agent": self.name, "data": {}, "summary": "缺少新闻数据"}

        analyzer = SentimentAnalyzer()
        analyzed_news = analyzer.analyze_news_batch(news_data)
        algo_summary = analyzer.get_sentiment_summary(analyzed_news)

        # ── LLM 校正情感分布 ──
        sample_news = analyzed_news[:25]
        samples_text = []
        for i, n in enumerate(sample_news):
            title = n.get("title", "")
            algo_label = n.get("sentiment_label", "neutral")
            algo_score = n.get("sentiment_score", 0)
            samples_text.append(
                f"{i+1}. [{algo_label} {algo_score:+.2f}] {title[:80]}"
            )

        llm_prompt = (
            f"共 {len(analyzed_news)} 条新闻，SnowNLP 算法结果："
            f"积极 {algo_summary.get('positive_count')} 条, "
            f"中性 {algo_summary.get('neutral_count')} 条, "
            f"负面 {algo_summary.get('negative_count')} 条。\n\n"
            f"⚠️ SnowNLP 对中文财经/政治文本存在严重正向偏置，"
            f"大量负面内容被误标为中性或正面。"
            f"请根据样本逐条校正情感标签。\n\n"
            f"前25条样本：\n" + "\n".join(samples_text) + "\n\n"
            f"输出 JSON（只输出 JSON）：\n"
            f'{{"corrected_positive": 数字, "corrected_negative": 数字, '
            f'"corrected_neutral": 数字, "corrected_avg_score": -1到1之间的数字, '
            f'"key_finding": "一句话核心发现"}}'
        )
        if feedback:
            llm_prompt += f"\n主持人指引: {feedback}"

        corrected = self._parse_sentiment_correction(llm_prompt, algo_summary)

        # ── 用 LLM 校正结果更新 summary ──
        summary = dict(algo_summary)
        summary["positive_count"] = corrected["positive_count"]
        summary["negative_count"] = corrected["negative_count"]
        summary["neutral_count"] = corrected["neutral_count"]
        total = max(corrected["positive_count"] + corrected["negative_count"] + corrected["neutral_count"], 1)
        summary["total_news"] = total
        summary["avg_sentiment"] = corrected["avg_sentiment"]
        summary["algo_positive_count"] = algo_summary.get("positive_count", 0)
        summary["algo_negative_count"] = algo_summary.get("negative_count", 0)
        summary["algo_neutral_count"] = algo_summary.get("neutral_count", 0)

        # ── 对个体新闻标签也做校正 ──
        if analyzed_news:
            self._apply_label_correction(analyzed_news, corrected)

        insight = corrected.get("key_finding", "")
        if insight and "Error" not in insight:
            self.write_to_forum_log(
                f"情绪分析完成（LLM校正后：正面{corrected['positive_count']}/"
                f"负面{corrected['negative_count']}/中性{corrected['neutral_count']}）。"
                f"核心发现: {insight}"
            )

        return {
            "status": "success",
            "agent": self.name,
            "data": {
                "analyzed_news": analyzed_news,
                "summary": summary
            },
            "summary": insight or f"情绪分析完成"
        }

    def _parse_sentiment_correction(self, prompt: str, algo_summary: dict) -> dict:
        response = self.call_llm(prompt)
        response = (response or "").strip()

        # 剥离 markdown 代码块
        if response.startswith("```"):
            response = re.sub(r"^```(?:json)?\s*\n?", "", response)
            response = re.sub(r"\n?```\s*$", "", response)
            response = response.strip()

        # 多级 JSON 提取
        def try_parse(text):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
            first = text.find("{")
            last = text.rfind("}")
            if first != -1 and last != -1 and last > first:
                try:
                    return json.loads(text[first:last+1])
                except json.JSONDecodeError:
                    pass
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            return None

        result = try_parse(response)
        if result and "corrected_positive" in result:
            return {
                "positive_count": int(result.get("corrected_positive", algo_summary.get("positive_count", 0))),
                "negative_count": int(result.get("corrected_negative", algo_summary.get("negative_count", 0))),
                "neutral_count": int(result.get("corrected_neutral", algo_summary.get("neutral_count", 0))),
                "avg_sentiment": float(result.get("corrected_avg_score", algo_summary.get("avg_sentiment", 0))),
                "key_finding": str(result.get("key_finding", "")),
            }

        # LLM 返回纯文本时，用启发式调整
        total = algo_summary.get("total_news", 1)
        pos = algo_summary.get("positive_count", 0)
        neg = max(1, int(total * 0.15))  # 至少有 15% 负面
        neu = total - pos - neg
        if neu < 0:
            neu = 0
        return {
            "positive_count": pos - int(neg * 0.3),
            "negative_count": neg + int(neg * 0.3),
            "neutral_count": neu,
            "avg_sentiment": algo_summary.get("avg_sentiment", 0) - 0.1,
            "key_finding": "SnowNLP 校正：算法对中文负面文本识别不足，已按经验比例调整",
        }

    @staticmethod
    def _apply_label_correction(analyzed_news: list, corrected: dict):
        """根据 LLM 校正结果，更新个体新闻的情感标签"""
        total = len(analyzed_news)
        target_neg = corrected.get("negative_count", 0)
        target_pos = corrected.get("positive_count", 0)

        # 按 SnowNLP 分数排序，最低分的标记为负面
        sorted_news = sorted(analyzed_news, key=lambda n: n.get("sentiment_score", 0))
        for i, news in enumerate(sorted_news):
            if i < target_neg:
                news["sentiment_label"] = "negative"
                news["sentiment_score"] = min(news.get("sentiment_score", 0), -0.15)
            elif i >= total - target_pos:
                news["sentiment_label"] = "positive"
                news["sentiment_score"] = max(news.get("sentiment_score", 0), 0.15)
            else:
                news["sentiment_label"] = "neutral"

if __name__ == "__main__":
    import streamlit as st
    st.title("SentimentAgent 独立测试")
    st.write("请集成到应用中测试。")
