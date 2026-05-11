import json
import re
from typing import Dict, Any, List
from .base_agent import BaseAgent


class ReportAgent(BaseAgent):
    def _get_system_prompt(self) -> str:
        return (
            "你是一个市场报告撰写者(ReportAgent)。"
            "负责对前面各个 Agent 的结论进行最终定稿摘要。"
        )

    def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        sentiment_summary = input_data.get("sentiment_summary", {})
        trend_summary = input_data.get("trend_summary", {})
        analyzed_news = input_data.get("analyzed_news", [])
        trend_results = input_data.get("trend_results", {})
        keyword = input_data.get("keyword", "未知关键词")
        task_id = input_data.get("task_id", "default")
        forum_log = input_data.get("forum_log", [])

        report_data = {
            "keyword": keyword,
            "task_id": task_id,
            "sentiment_summary": sentiment_summary,
            "trend_summary": trend_summary,
            "analyzed_news": analyzed_news,
            "trend_results": trend_results
        }

        # 论坛辩论过程提取
        forum_debate = self._extract_forum_debate(forum_log)
        report_data["forum_debate"] = forum_debate

        # 简单结语（概览 Tab 用）
        llm_prompt = (
            f"情绪均分: {sentiment_summary.get('avg_sentiment', 'N/A')}, "
            f"趋势方向: {trend_summary.get('trend_direction', 'N/A')}\n"
            "请用一段话(50字以内)生成针对最终报告的结语摘要。"
        )
        conclusion = self.call_llm(llm_prompt)

        if conclusion and "Error" not in conclusion:
            self.write_to_forum_log(f"已生成最终分析结论：{conclusion}")
        else:
            conclusion = f"针对 '{keyword}' 的综合舆情分析已完成，"
            trend = trend_summary.get("trend_direction", "平稳")
            avg_s = sentiment_summary.get("avg_sentiment", 0)
            if isinstance(avg_s, (int, float)) and avg_s > 0.1:
                conclusion += "市场情绪偏积极。"
            elif isinstance(avg_s, (int, float)) and avg_s < -0.1:
                conclusion += "市场情绪偏消极。"
            else:
                conclusion += "市场情绪总体平稳。"
            conclusion += f" 趋势预测{trend}。"

        report_data["conclusion"] = conclusion

        # AI 深度解读（AI 解读 Tab 专用）
        ai_insights = self._generate_ai_insights(
            keyword=keyword,
            sentiment_summary=sentiment_summary,
            trend_summary=trend_summary,
            analyzed_news=analyzed_news
        )
        ai_insights["forum_debate"] = forum_debate
        report_data["ai_insights"] = ai_insights

        # 生成结构化 debate_cards（供前端辩论区直接渲染）
        debate_cards = self._generate_debate_cards(forum_log, sentiment_summary, trend_summary)
        report_data["debate_cards"] = debate_cards
        ai_insights["debate_cards"] = debate_cards

        return {
            "status": "success",
            "agent": self.name,
            "data": {
                "report_data": report_data
            },
            "summary": conclusion
        }

    # ── 论坛辩论提取 ──────────────────────────────────────────
    @staticmethod
    def _extract_forum_debate(forum_log: list) -> list:
        """从 forum.log 原始行中提取结构化辩论时间线"""
        if not forum_log:
            return []

        # 过滤出 Agent 发言，跳过 SYSTEM 和日志头
        agent_pattern = re.compile(
            r'\[[\d\-:\s]+\]\s*\[(HOST|CollectAgent|SentimentAgent|TrendAgent|ReportAgent)\]\s*\[Round\s*(\d+)\]\s*(.+)'
        )
        debate_entries = []
        for line in forum_log:
            line = line.strip()
            if not line or "--- Forum Log" in line:
                continue
            m = agent_pattern.match(line)
            if not m:
                continue
            agent = m.group(1)
            round_num = int(m.group(2))
            content = m.group(3).strip()

            # 跳过无实质内容
            if len(content) < 5:
                continue

            # 分类
            entry_type = "insight"
            if agent == "HOST":
                entry_type = "summary"
            elif any(kw in content for kw in ["质疑", "不足", "错误", "置信度0", "建议暂停", "不可靠"]):
                entry_type = "challenge"
            elif any(kw in content for kw in ["建议", "应该", "请", "需要"]):
                entry_type = "action"

            # HOST 盲区提取
            blind_spots = []
            if agent == "HOST":
                for m2 in re.finditer(r'@(\w+)\s*[:：]?\s*([^@]+?)(?=@|【|$)', content):
                    spot = m2.group(2).strip()
                    if len(spot) > 3:
                        blind_spots.append(spot)
                # 也匹配 【盲区引导】 格式
                guide_match = re.search(r'【盲区引导】[：:]\s*(.+)', content)
                if guide_match:
                    parts = re.split(r'[@\n]', guide_match.group(1))
                    for p in parts:
                        p = p.strip()
                        if len(p) > 3 and p not in blind_spots:
                            blind_spots.append(p)
                # 兜底：LLM 未按格式输出时，提取含疑问/风险/不足的句子作为盲区
                if not blind_spots:
                    concern_kw = ["不足", "风险", "注意", "遗漏", "忽视", "缺失", "待验证", "不确定", "未知"]
                    for sent in re.split(r'[。；;?\n]', content):
                        sent = sent.strip()
                        if len(sent) < 8:
                            continue
                        if "?" in sent or "？" in sent or any(kw in sent for kw in concern_kw):
                            blind_spots.append(sent[:80])
                            if len(blind_spots) >= 3:
                                break

            # 提取核心观点：选最有观点性的句子（而非第一句）
            key_point = ReportAgent._pick_opinionated_sentence(content)
            if not key_point:
                key_point = content[:60]

            # 压缩内容：保留原话语气，过滤报告体词汇
            compressed = ReportAgent._compress_debate_content(content)

            debate_entries.append({
                "round": round_num,
                "agent": agent,
                "type": entry_type,
                "content": compressed,
                "key_point": key_point,
                "blind_spots": blind_spots,
            })

        # 按 round 和时间顺序排列
        debate_entries.sort(key=lambda e: (e["round"], {
            "CollectAgent": 0, "SentimentAgent": 1, "TrendAgent": 2, "HOST": 3, "ReportAgent": 4
        }.get(e["agent"], 5)))

        return debate_entries

    @staticmethod
    def _generate_debate_cards(forum_log: list, sentiment_summary: dict, trend_summary: dict) -> list:
        """从 forum.log 生成结构化辩论卡片，过滤过程日志，按 agent+round 合并，heuristic 生成 summary + highlights"""
        if not forum_log:
            return []

        agent_pattern = re.compile(
            r'\[[\d\-:\s]+\]\s*\[(HOST|CollectAgent|SentimentAgent|TrendAgent|ReportAgent)\]\s*\[Round\s*(\d+)\]\s*(.+)'
        )

        # ── Step A: 解析（状态机，多行 agent 内容追加到当前 entry）──
        entries = []
        current_entry = None
        for line in forum_log:
            line = line.strip()
            if not line or "--- Forum Log" in line:
                continue
            m = agent_pattern.match(line)
            if m:
                if current_entry and len(current_entry["content"]) >= 5:
                    entries.append(current_entry)
                agent, round_num, content = m.group(1), int(m.group(2)), m.group(3).strip()
                current_entry = {"agent": agent, "round": round_num, "content": content}
            elif current_entry:
                # 续行：追加到当前 entry（处理 agent 多行输出）
                current_entry["content"] += "\n" + line
        # 最后一个 entry
        if current_entry and len(current_entry["content"]) >= 5:
            entries.append(current_entry)

        # ── Step B: 过滤过程日志（HOST 不过滤）──
        process_kw = ["补充词", "新数据", "采集完成", "开始采集", "搜索完成",
                      "已采集", "源返回", "共获得", "搜索关键词", "开始搜索"]
        def _is_process_log(e):
            if e["agent"] == "HOST":
                return False
            if e["agent"] == "CollectAgent":
                if any(kw in e["content"] for kw in process_kw):
                    return True
            return False

        clean_entries = [e for e in entries if not _is_process_log(e)]

        # ── Step C: 按 agent+round 合并 ──
        agent_icon_map = {
            "CollectAgent": "📡", "SentimentAgent": "💬",
            "TrendAgent": "📈", "ReportAgent": "📄", "HOST": "🧑‍⚖️"
        }
        agent_label_map = {
            "CollectAgent": "采集Agent", "SentimentAgent": "情感Agent",
            "TrendAgent": "趋势Agent", "ReportAgent": "报告Agent", "HOST": "论坛主持人"
        }
        # 排序优先级
        priority_map = {"HOST": 0, "TrendAgent": 1, "SentimentAgent": 2, "CollectAgent": 3, "ReportAgent": 4}

        grouped = {}
        for e in clean_entries:
            key = (e["agent"], e["round"])
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(e)

        cards = []
        for (agent, rnd), items in sorted(grouped.items(), key=lambda x: (x[0][1], priority_map.get(x[0][0], 9))):
            if agent == "HOST":
                # 只取该 round 最后一条 HOST
                selected = items[-1]
            elif agent == "CollectAgent":
                # 优先取结论行（含采集完毕/共获取/有效数据/平台分布/采集完成/共采集/总计）
                conclusion_kw = ["采集完毕", "共获取", "有效数据", "平台分布", "采集完成", "共采集", "总计"]
                selected = None
                for it in items:
                    if any(kw in it["content"] for kw in conclusion_kw):
                        selected = it
                        break
                if not selected:
                    selected = max(items, key=lambda it: len(it["content"]))
            elif agent in ("SentimentAgent", "TrendAgent", "ReportAgent"):
                # 取该 round 最后一条
                selected = items[-1]
            else:
                selected = items[-1]

            # ── Step D: heuristic summary + highlights ──
            body = selected["content"]
            # HOST 盲区提取（复用已有正则）
            blind_spots = []
            if agent == "HOST":
                for m2 in re.finditer(r'@(\w+)\s*[:：]?\s*([^@]+?)(?=@|【|$)', body):
                    spot = m2.group(2).strip()
                    if len(spot) > 3:
                        blind_spots.append(spot)
                guide_match = re.search(r'【盲区引导】[：:]\s*(.+)', body)
                if guide_match:
                    for p in re.split(r'[@\n]', guide_match.group(1)):
                        p = p.strip()
                        if len(p) > 3 and p not in blind_spots:
                            blind_spots.append(p)
                if not blind_spots:
                    concern_kw = ["不足", "风险", "注意", "遗漏", "忽视", "缺失", "待验证", "不确定", "未知"]
                    for sent in re.split(r'[。；;?\n]', body):
                        sent = sent.strip()
                        if len(sent) < 8:
                            continue
                        if any(kw in sent for kw in concern_kw):
                            blind_spots.append(sent[:80])
                            if len(blind_spots) >= 3:
                                break

            # 清洗文本用于提取
            cleaned = re.sub(r'^#{1,6}\s+', '', body, flags=re.MULTILINE)
            cleaned = re.sub(r'\*{1,3}(.*?)\*{1,3}', r'\1', cleaned)

            # summary: 第一句非空话的完整句子
            bland_fragments = ["好的，以下", "好的，下面", "好的，接下来",
                               "以下是基于", "以下是基于现有", "基于现有数据与模型",
                               "下面是基于", "以下报告基于", "趋势综述", "以下为",
                               "综合分析", "基于以上", "综合来看", "总体而言",
                               "据分析", "根据当前", "据此"]
            def _is_bland(sentence):
                return any(frag in sentence for frag in bland_fragments)

            summary = ""
            sentences = re.split(r'[。！？]', cleaned)
            for s in sentences:
                s = s.strip()
                if len(s) < 8:
                    continue
                if _is_bland(s):
                    continue
                if re.match(r'^[\d#\*\s]+', s):
                    continue
                summary = s[:60]
                break
            if not summary:
                # fallback: 取 content 最长一行（跳过极短行和 bland 行）
                lines = [l.strip() for l in cleaned.split('\n') if len(l.strip()) > 8]
                best = ""
                for l in lines:
                    if not _is_bland(l) and len(l) > len(best):
                        best = l
                summary = (best or cleaned)[:60]

            # highlights: 2-3 条质量句子
            highlights = []
            for s in sentences:
                s = s.strip()
                if len(s) < 15:
                    continue
                if re.match(r'^[\d#\*\s\-]+', s):
                    continue
                if _is_bland(s):
                    continue
                if s == summary:
                    continue
                highlights.append(s[:80])
                if len(highlights) >= 3:
                    break

            cards.append({
                "agent": agent,
                "agent_label": agent_label_map.get(agent, agent),
                "agent_icon": agent_icon_map.get(agent, "📋"),
                "round": rnd,
                "summary": summary,
                "highlights": highlights,
                "full_text": cleaned[:500],
                "blind_spots": blind_spots,
                "priority": priority_map.get(agent, 9),
            })

        return cards

    @staticmethod
    def _pick_opinionated_sentence(content: str) -> str:
        """选出最有观点性的一句，而非简单取第一句。
        评分标准：包含强判断词（置信度 X%、严禁、严重、不能用、风险）的句子得分更高"""
        sentences = re.split(r'[。；;]', content)
        if not sentences:
            return ""
        strong_words = [
            "置信度0", "严禁", "严重", "不能用", "统计噪声", "风险", "必须",
            "不能", "错误", "质疑", "不足", "不可", "暂停", "警告", "注意",
            "关键", "核心", "紧急", "危机", "崩", "暴跌", "飙升"
        ]
        best_sentence = ""
        best_score = -1
        for s in sentences:
            s = s.strip()
            if len(s) < 8:
                continue
            score = len(s)  # 基础分：句子长度
            for w in strong_words:
                if w in s:
                    score += 20  # 强判断词加权
            # 报告体弱化词扣分
            for w in ["综合来看", "总体而言", "据此", "整体上", "较为"]:
                if w in s:
                    score -= 10
            if score > best_score:
                best_score = score
                best_sentence = s
        return best_sentence[:70].strip()

    @staticmethod
    def _compress_debate_content(content: str) -> str:
        """压缩 Agent 发言，保留原话语气，过滤报告体废话前缀"""
        # 剥离报告体前缀
        prefixes = [
            "据此判断，", "综合来看，", "总体而言，", "根据当前数据，",
            "我的分析显示，", "经分析，", "基于以上数据，", "整体上，",
            "分析发现，", "结果表明，"
        ]
        for pf in prefixes:
            if content.startswith(pf):
                content = content[len(pf):]
                break
        # 截断到 120 字，在句号处断
        if len(content) <= 120:
            return content
        truncated = content[:120]
        last_period = max(truncated.rfind("。"), truncated.rfind("；"), truncated.rfind(";"))
        if last_period > 40:
            return truncated[:last_period + 1]
        return truncated + "…"

    @staticmethod
    def _parse_markdown_insights(text: str, keyword: str) -> dict:
        """当 LLM 输出 Markdown 结构（## 标题 + 段落）而非 JSON 时的兜底解析"""
        if not text or "{" in text:
            return {}  # 有 { 说明可能含 JSON，不在此处理

        # 检测 Markdown 结构特征
        has_headings = bool(re.search(r'^#{1,4}\s+', text, re.MULTILINE))
        if not has_headings:
            return {}

        # 提取 headline：第一个 ## 标题
        headline_match = re.search(r'^#{1,2}\s*(?:[\d.]+\s*)?(.+?)$', text, re.MULTILINE)
        headline = headline_match.group(1).strip()[:25] if headline_match else f"{keyword}舆情洞察"

        # 提取各段小标题作为 insights
        sections = re.split(r'\n(?=#{2,4}\s+)', text)
        insights = []
        type_keywords = {
            "opportunity": ["机会", "利好", "正面", "优势", "增长"],
            "risk": ["风险", "危机", "负面", "威胁", "隐患", "问题"],
            "anomaly": ["异常", "反常识", "反共识", "意外", "矛盾", "反常", "悖论", "泡沫"],
            "trend": ["趋势", "走向", "方向", "预测", "前景"],
        }

        for sec in sections:
            title_match = re.search(r'^#{2,4}\s*(?:[\d.]+\s*)?(.+?)$', sec, re.MULTILINE)
            if not title_match:
                continue
            heading_level = len(title_match.group(0)) - len(title_match.group(0).lstrip('#'))
            title = title_match.group(1).strip()[:20]
            # 只处理 ### / #### 的 insight 级别标题，跳过 ## 的章节标题
            if heading_level <= 2:
                continue
            # 提取段落正文（标题之后的内容）
            body_start = title_match.end()
            body = sec[body_start:].strip()
            # 清理正文
            body = re.sub(r'\n+', ' ', body)[:120]

            # 判断类型
            ins_type = "trend"
            for t, kws in type_keywords.items():
                if any(kw in title + body for kw in kws):
                    ins_type = t
                    break

            # 判断是否为反共识
            contrarian = any(w in title + body for w in ["反直觉", "反共识", "悖论", "异常", "表面", "隐藏"])

            # 提取置信度
            conf_match = re.search(r'(\d{1,3})%', body)
            confidence = float(int(conf_match.group(1)) / 100) if conf_match else 0.6

            if len(body) > 10:
                insights.append({
                    "type": ins_type,
                    "title": title[:8],
                    "claim": body[:60],
                    "evidence": body[:100],
                    "why_now": "基于当前舆情数据实时分析",
                    "confidence": min(0.95, max(0.1, confidence)),
                    "contrarian": contrarian,
                })

        if len(insights) < 2:
            return {}

        # 提取 action_signal
        neg_words = sum(1 for w in ["风险", "危机", "负面", "下跌", "崩"] if w in text)
        pos_words = sum(1 for w in ["机会", "利好", "增长", "正面", "突破"] if w in text)
        if neg_words > pos_words + 1:
            action_signal = "watch_out"
        elif pos_words > neg_words + 2:
            action_signal = "buy_attention"
        elif neg_words > 0 and pos_words > 0:
            action_signal = "neutral"
        else:
            action_signal = "neutral"

        # 提取盲区（以 ? 或 ？ 结尾的句子）
        blind_spots = []
        for sent in re.split(r'[。\n]', text):
            sent = sent.strip()
            if ("?" in sent or "？" in sent) and len(sent) > 8:
                blind_spots.append(sent[:80])

        return {
            "headline": headline,
            "action_signal": action_signal,
            "insights": insights[:6],
            "blind_spots": blind_spots[:3] or ["现有数据时间跨度有限，长期趋势待验证"],
            "one_week_prediction": "",
        }

    # ── AI 深度解读 ──────────────────────────────────────────────
    def _generate_ai_insights(
        self,
        keyword: str,
        sentiment_summary: dict,
        trend_summary: dict,
        analyzed_news: list
    ) -> dict:

        total = sentiment_summary.get("total_news", len(analyzed_news)) or 1
        pos_pct = sentiment_summary.get("positive_count", 0) / max(total, 1)
        neg_pct = sentiment_summary.get("negative_count", 0) / max(total, 1)
        neu_pct = sentiment_summary.get("neutral_count", 0) / max(total, 1)
        avg_score = sentiment_summary.get("avg_sentiment", 0)

        system_prompt = """你是一个 JSON 输出机。你的回答必须以 { 开头、以 } 结尾，只输出一段合法的 JSON。

你是顶级对冲基金的首席舆情分析师，你的判断直接影响千万级投资决策。

【铁律】
1. 禁止输出任何非 JSON 内容，包括 Markdown 标题、代码块标记、解释性文字
2. 只输出一个 JSON 对象，第一个字符是 {，最后一个字符是 }
3. 如果输出非 JSON 内容，你的回答将被完全丢弃
4. 必须包含至少1个反直觉或反共识的观点，标记 contrarian: true
5. 禁止使用以下词汇：整体均衡、值得关注、总体来看、有所提升、存在一定、较为、相对
6. 每个 claim 必须是可被证伪的具体判断

JSON 格式（严格遵循，不要修改 key 名）：
{
    "headline": "一句话核心判断，不超过25字，必须有明确立场和倾向",
    "action_signal": "strong_buy_attention | buy_attention | neutral | watch_out | alert",
    "insights": [
        {
            "type": "opportunity | risk | anomaly | trend",
            "title": "洞察标题，8字以内",
            "claim": "具体判断，不超过50字",
            "evidence": "数据或现象依据",
            "why_now": "为什么现在重要，不超过30字",
            "confidence": 0.0到1.0之间的数字,
            "contrarian": true或false
        }
    ],
    "blind_spots": ["现有数据无法回答的关键问题，2-3条"],
    "one_week_prediction": "未来7天最可能发生的具体事件，一句话"
}"""

        user_prompt = f"""分析对象：{keyword}

情感分布数据：
- 正面：{pos_pct:.1%}
- 负面：{neg_pct:.1%}
- 中性：{neu_pct:.1%}
- 综合情感得分：{avg_score:.3f}

新闻样本（前20条）：
{self._format_posts(analyzed_news[:20])}

关键词：
{', '.join(self._extract_keywords(analyzed_news)[:20])}

趋势预测：
- 方向：{trend_summary.get('trend_direction', 'N/A')}
- 置信度：{trend_summary.get('confidence', 0)}

请基于以上数据，输出你的舆情洞察分析 JSON。

⚠️ 强制要求：
1. 只输出 JSON，不要输出任何 JSON 以外的文字
2. 不要用代码块标记包裹
3. 第一个字符必须是左大括号，最后一个字符必须是右大括号
4. 如果违反以上任何一条，你的回答将被视为无效"""

        response = self.call_llm_with_system(system_prompt, user_prompt, temperature=0.1)
        response = response.strip()

        # ── 多级兜底：强制提取 JSON ──
        # Level 1: 剥离 markdown 代码块
        if response.startswith("```"):
            response = re.sub(r"^```(?:json)?\s*\n?", "", response)
            response = re.sub(r"\n?```\s*$", "", response)
            response = response.strip()

        # Level 2: 直接解析
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # Level 3: 找到第一个 { 到最后一个 } 之间的内容
        first_brace = response.find("{")
        last_brace = response.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            json_candidate = response[first_brace:last_brace + 1]
            try:
                return json.loads(json_candidate)
            except json.JSONDecodeError:
                pass

        # Level 4: 正则兜底
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        # Level 5: Markdown 结构解析（LLM 输出了 ## Title 格式时）
        md_parsed = self._parse_markdown_insights(response, keyword)
        if md_parsed:
            return md_parsed

        return {
            "headline": response[:100] if response else "分析生成失败",
            "insights": [],
            "blind_spots": [f"LLM 返回格式异常，请重试。原始响应前200字符: {response[:200]}"],
            "action_signal": "neutral",
            "one_week_prediction": ""
            }

    @staticmethod
    def _format_posts(news_list: list) -> str:
        lines = []
        for i, n in enumerate(news_list[:20]):
            title = n.get("title", "") if isinstance(n, dict) else str(n)
            score = n.get("sentiment_score", 0) if isinstance(n, dict) else 0
            src = n.get("source", "") if isinstance(n, dict) else ""
            lines.append(f"{i+1}. [{score:+.2f}] {title} (来源:{src or '未知'})")
        return "\n".join(lines) if lines else "(无新闻数据)"

    @staticmethod
    def _extract_keywords(news_list: list) -> List[str]:
        titles = []
        for n in news_list[:50]:
            if isinstance(n, dict):
                t = n.get("title", "")
                if t:
                    titles.append(t)
        if not titles:
            return []
        try:
            import jieba.analyse
            combined = "。".join(titles)
            keywords = jieba.analyse.extract_tags(combined, topK=20)
            return keywords
        except Exception:
            return []
