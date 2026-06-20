import json
import re
from typing import Dict, Any
from .base_agent import BaseAgent
from ..analysis.sentiment_analysis import SentimentAnalyzer

class SentimentAgent(BaseAgent):
    def _get_system_prompt(self) -> str:
        return (
            "你是一个极其悲观的危机分析师(Red Team / SentimentAgent)。\n"
            "你会收到基础的情绪打分结果和新闻样本，你需要进行两项工作：\n"
            "1. 输出结构化的情感分布校正结果（必须保留 JSON 格式用于图表渲染）。\n"
            "2. 输出一篇极具对抗性的【危机研判报告】（Markdown格式）。\n"
            "作为红方，你的职责是挑刺、放大数据中的负面情绪，推演最坏的连锁反应（如股市崩盘、赞助商撤资、公关危机）。\n"
            "如果这是第二轮发言，你必须猛烈抨击蓝方(TrendAgent)的乐观预判！"
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
            f"共 {len(analyzed_news)} 条新闻，FinBERT 算法初始结果："
            f"积极 {algo_summary.get('positive_count')} 条, 中性 {algo_summary.get('neutral_count')} 条, 负面 {algo_summary.get('negative_count')} 条。\n\n"
            f"前25条样本：\n" + "\n".join(samples_text) + "\n\n"
            f"请严格按以下格式输出（先 JSON，后 Markdown）：\n"
            f"```json\n"
            f'{{\n  "corrected_positive": 数字,\n  "corrected_negative": 数字,\n  "corrected_neutral": 数字,\n  "corrected_avg_score": 数字,\n  "key_finding": "一句话核心危机发现"\n}}\n'
            f"```\n\n"
            f"【红方视角：深度危机研判】\n"
            f"1. 危机警报（一句话概括最大的风险）\n"
            f"2. 极端情绪抓取（从样本中挑出最极端的负面情绪）\n"
            f"3. 连锁破坏推演（推演最坏的商业/社会影响）\n"
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
        markdown_report = corrected.get("markdown", "")
        
        if markdown_report:
            self.write_to_forum_log(f"【总结】：{insight}\n\n{markdown_report}")
        elif insight:
            self.write_to_forum_log(f"【总结】：{insight}")

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

        # 尝试提取 JSON 和后面的 Markdown
        json_str = response
        markdown_str = ""
        
        # 如果包含 markdown block
        json_match = re.search(r'```(?:json)?(.*?)```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1).strip()
            # 找到 JSON 块之后的内容作为 markdown
            markdown_str = response[json_match.end():].strip()
        else:
            # 找大括号
            first = response.find('{')
            last = response.rfind('}')
            if first != -1 and last != -1 and last > first:
                json_str = response[first:last+1]
                markdown_str = response[last+1:].strip()

        def try_parse(text):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return None

        result = try_parse(json_str)
        if result and "corrected_positive" in result:
            return {
                "positive_count": int(result.get("corrected_positive", algo_summary.get("positive_count", 0))),
                "negative_count": int(result.get("corrected_negative", algo_summary.get("negative_count", 0))),
                "neutral_count": int(result.get("corrected_neutral", algo_summary.get("neutral_count", 0))),
                "avg_sentiment": float(result.get("corrected_avg_score", algo_summary.get("avg_sentiment", 0))),
                "key_finding": str(result.get("key_finding", "")),
                "markdown": markdown_str
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
            "key_finding": "FinBERT 基础分类完成：已进行经验权重调整",
        }

    @staticmethod
    def _apply_label_correction(analyzed_news: list, corrected: dict):
        """根据 LLM 校正结果，更新个体新闻的情感标签"""
        total = len(analyzed_news)
        target_neg = corrected.get("negative_count", 0)
        target_pos = corrected.get("positive_count", 0)
        # 防止 neg + pos > total 导致同一条新闻同时被标为负和正
        target_neg = min(target_neg, total - target_pos)

        # 按 FinBERT 融合分数排序，最低分的标记为负面
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

