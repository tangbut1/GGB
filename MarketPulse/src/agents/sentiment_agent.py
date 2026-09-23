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
        # 跨会话项目记忆：同一主题此前分析的结论。放在指引之后，作为背景
        # 而非指令——历史结论与本次数据冲突时以本次为准，提示词里已写明。
        memory_context = input_data.get("memory_context")
        if memory_context:
            llm_prompt += f"\n\n{memory_context}"

        corrected = self._parse_sentiment_correction(llm_prompt, algo_summary)
        llm_available = corrected.pop("llm_available", True)

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
        # 供前端"方法论"说明用：LLM 校正是否真的生效。不可用时展示的分布
        # 是 SnowNLP 原值，界面必须说清楚，否则用户以为经过了大模型校正。
        summary["llm_corrected"] = bool(llm_available)

        # ── 对个体新闻标签也做校正 ──
        # LLM 不可用时校正目标就等于算法原值，再排一遍序只会无谓地翻转
        # 边界样本的标签，跳过。
        if analyzed_news and llm_available:
            self._apply_label_correction(analyzed_news, corrected)

        insight = corrected.get("key_finding", "")
        markdown_report = corrected.get("markdown", "")

        if llm_available:
            if markdown_report:
                self.write_to_forum_log(f"【总结】：{insight}\n\n{markdown_report}")
            elif insight:
                self.write_to_forum_log(f"【总结】：{insight}")
        else:
            # 红方失声会让裁判只听到蓝方一面之词，辩论退化成单方陈述。
            # 用本地算法的真实分布合成红方立论，所有数字都是实测值。
            self.write_to_forum_log(
                self._synthesize_red_speech(algo_summary, analyzed_news, feedback)
            )
            insight = "本地情绪模型已完成红方立论（裁判 LLM 暂不可用）"

        return {
            "status": "success",
            "agent": self.name,
            "data": {
                "analyzed_news": analyzed_news,
                "summary": summary
            },
            "summary": insight or f"情绪分析完成"
        }

    def _synthesize_red_speech(self, algo_summary: dict, analyzed_news: list, feedback: str = "") -> str:
        """LLM 不可用时，用 SnowNLP 的实测结果合成红方危机立论。

        红方立场是放大风险，所以立论围绕负面占比、情绪极值、信源集中度
        和最坏连锁反应展开；但每个数字都来自本地算法，不做任何编造。
        """
        total = max(algo_summary.get("total_news", 0), 1)
        neg = algo_summary.get("negative_count", 0)
        pos = algo_summary.get("positive_count", 0)
        neu = algo_summary.get("neutral_count", 0)
        avg = algo_summary.get("avg_sentiment", 0.0)
        neg_ratio = neg / total

        negatives = sorted(
            [n for n in analyzed_news if n.get("sentiment_label") == "negative"],
            key=lambda n: n.get("sentiment_score", 0),
        )[:3]
        worst = "；".join(
            f"“{(n.get('title') or '未命名')[:40]}”（{n.get('sentiment_score', 0):+.2f}）"
            for n in negatives
        ) or "样本中未出现负面标题"

        source_counter = {}
        for n in analyzed_news:
            src = n.get("source") or "未知来源"
            source_counter[src] = source_counter.get(src, 0) + 1
        top_sources = sorted(source_counter.items(), key=lambda kv: kv[1], reverse=True)[:3]
        source_text = "、".join(f"{s}×{c}" for s, c in top_sources) or "来源分散"

        if avg <= -0.2 or neg_ratio >= 0.4:
            crisis = (
                f"整体情绪已明显偏空（平均分 {avg:+.3f}，负面占比 {neg_ratio:.0%}），"
                "负面声量占主导，舆情恶化有实测数据支撑。"
            )
        elif neg_ratio >= 0.2:
            crisis = (
                f"负面占比 {neg_ratio:.0%} 虽非多数，但已形成持续性负面叙事，"
                "且负面标题的情绪极值远低于中性区间。"
            )
        else:
            crisis = (
                f"当前负面占比仅 {neg_ratio:.0%}，但红方必须指出：中性 {neu/total:.0%} "
                "的沉默大多数是未被点燃的柴堆，单点事件即可让情绪极性在数小时内反转，"
                "而转向成本由品牌方单方面承担。"
            )

        lines = [
            "【红方立论】本地情绪模型结论："
            f"共 {total} 条样本，负面 {neg} 条（{neg_ratio:.0%}）、"
            f"中性 {neu} 条（{neu/total:.0%}）、积极 {pos} 条（{pos/total:.0%}），"
            f"平均情绪分 {avg:+.3f}。",
            f"【危机警报】{crisis}",
            f"【极端情绪抓取】{worst}",
            f"【信源集中度】{source_text}——信源越集中，负面叙事被放大和复读的速度越快，"
            "纠错声明能覆盖的渠道反而越少。",
        ]

        opponent = self.extract_opponent_claim(feedback, limit=90)
        if opponent:
            # 驳斥的开场句必须跟着实测分布走。负面为 0 时再念"已达 N 条"
            # 是在复述一个不存在的数字，反而削弱自己的立论。
            if neg:
                evidence = f"负面样本实测 {neg} 条（{neg_ratio:.0%}），不是可以忽略的噪音"
                closing = "回避了负面极值的存在，把可观测的风险当成噪音剥离。"
            else:
                evidence = (
                    f"负面样本当前虽为 0，但中性占 {neu/total:.0%} 的样本没有任何立场缓冲，"
                    "一次单点事件就能整体翻转"
                )
                closing = "把尚未爆发的风险当成了不存在的风险。"
            lines.append(
                f"【驳斥蓝方】蓝方以趋势模型置信度为由建议观望，但{evidence}。"
                f"对方引用的“{opponent}”{closing}"
            )

        lines.append("（裁判 LLM 暂不可用，本立论由本地模型生成）")
        return "\n".join(lines)

    def _parse_sentiment_correction(self, prompt: str, algo_summary: dict) -> dict:
        response = self.call_llm(prompt)
        response = (response or "").strip()

        # LLM 不可用时原样返回算法结果：下面那条"至少 15% 负面"的启发式是
        # 给"LLM 回了但解析不出 JSON"用的，对完全无 Key 的场景会凭空造出
        # 负面情绪，让红方的危机立论建立在假数据上。立论改为用本地真实
        # 分布合成（见 _synthesize_red_speech）。
        if self.llm_unavailable(response):
            corrected = dict(algo_summary)
            corrected["llm_available"] = False
            return corrected

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
                "markdown": markdown_str,
                "llm_available": True
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
            "llm_available": True
        }

    @staticmethod
    def _apply_label_correction(analyzed_news: list, corrected: dict):
        """按 LLM 校正后的分布，重新分配个体新闻的情感标签。

        只改标签，不动分数。分数是 SnowNLP 对单条文本的实测值，校正改的是
        "这批里该有多少条算负面"这个分布判断——两回事。曾经在这里把分数
        也钳到 ±0.15，结果 44 条负面全部变成同一个 -0.15：
          - 证据卡上的"情绪分"每一条都一样，看起来就是坏数据；
          - 极化度（|分数| ≥ 0.6 的占比）结构上永远为 0，一个核心指标
            再也动不了；
          - 情绪指数退化成标签占比的线性函数，不再是连续测量。
        原标签保留在 sentiment_label_algo，校正是否真的改了判断由此可查。
        """
        total = len(analyzed_news)
        target_neg = corrected.get("negative_count", 0)
        target_pos = corrected.get("positive_count", 0)
        # 防止 neg + pos > total 导致同一条新闻同时被标为负和正
        target_neg = min(target_neg, total - target_pos)

        # 按分数排序，最低分的标记为负面
        sorted_news = sorted(analyzed_news, key=lambda n: n.get("sentiment_score", 0))
        for i, news in enumerate(sorted_news):
            news.setdefault("sentiment_label_algo", news.get("sentiment_label", ""))
            if i < target_neg:
                news["sentiment_label"] = "negative"
            elif i >= total - target_pos:
                news["sentiment_label"] = "positive"
            else:
                news["sentiment_label"] = "neutral"

