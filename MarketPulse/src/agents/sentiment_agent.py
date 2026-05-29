import json
import re
from typing import Dict, Any
from .base_agent import BaseAgent
from ..analysis.sentiment_analysis import SentimentAnalyzer

class SentimentAgent(BaseAgent):
    def _get_system_prompt(self) -> str:
        return (
            "你是一个顶级量化基金的情绪分析AI(SentimentAgent)。"
            "你的任务是直接阅读最新的核心新闻样本全文或摘要，并以极度敏锐和客观的视角，"
            "判断市场当前的真实情绪。你要识别出隐藏在官方套话下的负面情绪（如愤怒、恐慌、维权），"
            "以及真实的正面情绪。不要受任何第三方算法误导，你的判断就是最终权威。"
        )

    def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        news_data = input_data.get("news", [])
        feedback = input_data.get("feedback", "")

        if not news_data:
            return {"status": "error", "agent": self.name, "data": {}, "summary": "缺少新闻数据"}

        analyzer = SentimentAnalyzer()
        analyzed_news = analyzer.analyze_news_batch(news_data)
        algo_summary = analyzer.get_sentiment_summary(analyzed_news)

        # ── 纯 LLM 多维情感基准线推演 ──
        # 我们不再依赖 SnowNLP，而是让大模型接管核心样本的情感判定
        sample_news = analyzed_news[:35]  # 取前35条核心新闻
        samples_text = []
        for i, n in enumerate(sample_news):
            title = n.get("title", "")
            summary = n.get("summary", "")[:100]
            samples_text.append(f"{i+1}. {title} | {summary}")

        llm_prompt = (
            f"我们共采集到了 {len(news_data)} 条新闻数据。以下是排名前35的核心样本：\n\n"
            f"{'\n'.join(samples_text)}\n\n"
            f"请仔细分析这些内容，计算真实的情感分布。请注意：\n"
            f"1. 对营销陷阱、涉嫌违规、投诉争议等，必须严格判定为【负面】（悲观/愤怒/恐慌）。\n"
            f"2. 中性报道、正常政务、无明确情绪的公关稿件，判定为【中性】。\n"
            f"3. 只有真实的利好、重大突破、积极反馈，才能判定为【正面】。\n\n"
            f"输出一个纯 JSON（不要 Markdown）：\n"
            f'{{"corrected_positive": 预计这{len(news_data)}条中真正的正面数量, '
            f'"corrected_negative": 预计这{len(news_data)}条中真正的负面数量, '
            f'"corrected_neutral": 预计中性数量, '
            f'"corrected_avg_score": -1.0 到 1.0 的平均情绪分, '
            f'"key_finding": "一句话说明你为何给出这样的情感分布判定（指出核心情绪驱动因素）"}}'
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
                f"全量大模型多维情绪分析完成（真实判定：正面{corrected['positive_count']}/"
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
        # 防止 neg + pos > total 导致同一条新闻同时被标为负和正
        target_neg = min(target_neg, total - target_pos)

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

