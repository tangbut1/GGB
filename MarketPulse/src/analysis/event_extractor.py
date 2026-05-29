import json
import re
from collections import Counter
from typing import Any, Dict, List, Optional

try:
    import jieba
    import jieba.analyse
except ImportError:
    jieba = None


class EventExtractor:
    """从已分析新闻中提取关键事件并构建因果关系图谱。

    主路径: LLM 抽取 SPO 三元组 → 因果/时序/对抗边分类
    降级路径: jieba TF-IDF + 共现 (LLM 不可用时)
    """

    def __init__(
        self,
        top_k: int = 20,
        edge_k: int = 12,
        llm_config: Optional[Dict[str, Any]] = None,
        llm_call_fn=None,
    ):
        self.top_k = top_k
        self.edge_k = edge_k
        self._llm_config = llm_config or {}
        self._llm_call_fn = llm_call_fn

    # ── Public API ────────────────────────────────────────────────

    def extract_events(
        self, analyzed_news: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """主入口：输入已做情感分析的新闻列表，输出 nodes + edges。"""
        if not analyzed_news:
            return {"nodes": [], "edges": []}

        # 优先 LLM 路径
        if self._llm_call_fn or self._llm_config:
            try:
                result = self._extract_with_llm(analyzed_news)
                if result["nodes"] or result["edges"]:
                    return result
            except Exception:
                pass

        # 降级: jieba 共现路径
        return self._extract_with_keywords(analyzed_news)

    # ── LLM Path: SPO Triple Extraction ───────────────────────────

    def _extract_with_llm(
        self, analyzed_news: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Use LLM to extract Subject-Predicate-Object triples with causal typing."""
        # Build compact news context
        news_items = []
        for item in analyzed_news[:15]:
            if not isinstance(item, dict):
                continue
            title = item.get("title", "")[:80]
            summary = (item.get("summary") or item.get("content") or "")[:120]
            sent = item.get("sentiment_label", "neutral")
            news_items.append(f"[{sent}] {title} | {summary}")

        if not news_items:
            return {"nodes": [], "edges": []}

        prompt = self._build_triple_prompt(news_items)
        response = self._call_llm(prompt)

        try:
            triples = self._parse_triple_response(response)
        except Exception:
            return {"nodes": [], "edges": []}

        return self._triples_to_graph(triples, analyzed_news)

    def _build_triple_prompt(self, news_items: List[str]) -> str:
        items_text = "\n".join(f"{i+1}. {item}" for i, item in enumerate(news_items))
        return (
            "你是一名金融事件图谱分析师。从以下新闻中提取事件之间的因果关系，输出严格的 JSON。\n\n"
            "## 规则\n"
            "1. 提取 (主体 Subject, 动作 Predicate, 客体 Object) 三元组，每个三元组的 S、P、O 用 2-8 个汉字表达\n"
            "2. 为每个三元组分类关系类型: causal(因果), temporal(时序先后), adversarial(对立/对抗)\n"
            "3. 给出 0-1 之间的置信度\n"
            "4. 避免重复三元组；只提取有信息量的关系，忽略常识性关联\n"
            "5. 输出格式必须是纯 JSON，不要包含 markdown 代码块标记\n\n"
            "## 新闻\n"
            f"{items_text}\n\n"
            "## 输出格式\n"
            '{"triples": [{"subject": "...", "predicate": "...", "object": "...", '
            '"type": "causal|temporal|adversarial", "confidence": 0.0}]}\n'
        )

    def _call_llm(self, prompt: str) -> str:
        if self._llm_call_fn:
            return self._llm_call_fn(prompt)

        import requests
        cfg = self._llm_config
        base_url = cfg.get("base_url", "").rstrip("/")
        if not base_url.endswith("/chat/completions"):
            base_url = f"{base_url}/chat/completions"
        api_key = cfg.get("api_key", "")
        model = cfg.get("model", "gpt-3.5-turbo")

        resp = requests.post(
            base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are a financial event graph analyst. Output valid JSON only."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
            },
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        return body["choices"][0]["message"]["content"]

    @staticmethod
    def _parse_triple_response(response: str) -> List[Dict[str, Any]]:
        # 4-level JSON extraction fallback
        raw = response.strip()
        # Level 1: direct parse
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and "triples" in data:
                return data["triples"]
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass
        # Level 2: strip code fences
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            data = json.loads(cleaned)
            if isinstance(data, dict) and "triples" in data:
                return data["triples"]
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass
        # Level 3: find JSON slice
        m = re.search(r"\{[\s\S]*\"triples\"[\s\S]*\}", raw)
        if m:
            try:
                return json.loads(m.group())["triples"]
            except (json.JSONDecodeError, KeyError):
                pass
        # Level 4: regex extract individual triples
        return []

    def _triples_to_graph(
        self,
        triples: List[Dict[str, Any]],
        analyzed_news: List[Dict[str, Any]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Convert SPO triples to nodes + typed edges."""
        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []
        node_ids: Dict[str, int] = {}
        edge_set = set()

        edge_colors = {
            "causal": "#e74c3c",
            "temporal": "#3498db",
            "adversarial": "#e67e22",
        }
        edge_labels = {
            "causal": "因果",
            "temporal": "时序",
            "adversarial": "对抗",
        }

        for t in triples:
            subj = str(t.get("subject", "")).strip()
            pred = str(t.get("predicate", "")).strip()
            obj = str(t.get("object", "")).strip()
            etype = str(t.get("type", "causal")).strip()
            conf = float(t.get("confidence", 0.5))

            if not subj or not obj or len(subj) < 2 or len(obj) < 2:
                continue

            # Register nodes
            for name in (subj, obj):
                if name not in node_ids:
                    nid = len(nodes) + 1
                    node_ids[name] = nid
                    sentiment_label = self._infer_sentiment(name, analyzed_news)
                    nodes.append({
                        "id": nid,
                        "label": name[:22],
                        "type": "事件",
                        "sentiment_type": sentiment_label,
                        "desc": f"实体: {name}",
                        "date": "",
                        "sentiment": {"positive": "正面", "negative": "负面", "neutral": "中性"}.get(sentiment_label, "中性"),
                        "strength": round(conf, 2),
                        "weight": max(1, int(conf * 10)),
                    })

            # Register edge (avoid duplicates)
            frm = node_ids[subj]
            to = node_ids[obj]
            edge_key = (frm, to, etype)
            if edge_key in edge_set:
                continue
            edge_set.add(edge_key)
            node_ids.setdefault(subj, frm)
            node_ids.setdefault(obj, to)

            color = edge_colors.get(etype, "#888888")
            label = edge_labels.get(etype, etype)

            edges.append({
                "from": frm,
                "to": to,
                "type": etype,
                "rel": etype,
                "color": color,
                "label": f"{pred}({label})",
                "weight": round(conf * 5, 1),
                "confidence": conf,
                "predicate": pred,
            })

        return {"nodes": nodes, "edges": edges[: self.edge_k * 4]}

    @staticmethod
    def _infer_sentiment(name: str, news_list: List[Dict[str, Any]]) -> str:
        """Infer sentiment polarity for a node from related news."""
        pos = neg = neu = 0
        for n in news_list:
            if not isinstance(n, dict):
                continue
            title = n.get("title", "")
            if name not in title:
                continue
            lbl = (n.get("sentiment_label") or "").lower()
            if lbl == "positive":
                pos += 1
            elif lbl == "negative":
                neg += 1
            else:
                neu += 1
        if neg > pos and neg > neu:
            return "negative"
        if pos > neg and pos > neu:
            return "positive"
        return "neutral"

    # ── Fallback Path: jieba Keyword Co-occurrence ─────────────────

    def _extract_with_keywords(
        self, analyzed_news: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Jieba-based keyword extraction + co-occurrence (fallback when LLM unavailable)."""
        keyword_nodes = self._extract_keyword_nodes(analyzed_news)

        for news in analyzed_news:
            if not isinstance(news, dict):
                continue
            matched = self._match_keywords(news.get("title", ""), keyword_nodes)
            for kw in matched:
                keyword_nodes[kw]["news_refs"] += 1

        nodes = self._build_nodes(keyword_nodes, analyzed_news)
        edges = self._build_edges(nodes, analyzed_news)
        return {"nodes": nodes, "edges": edges}

    def _extract_keyword_nodes(
        self, news_list: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        all_titles = []
        for news in news_list:
            title = news.get("title", "")
            if title and isinstance(title, str):
                all_titles.append(title)

        if not all_titles:
            return {}

        combined = "。".join(all_titles)
        if jieba:
            keywords = jieba.analyse.extract_tags(combined, topK=self.top_k, withWeight=True)
        else:
            tokens = re.findall(r'[一-龥]{2,}|[A-Za-z][A-Za-z0-9_-]+', combined)
            counts = Counter(tokens)
            total = max(sum(counts.values()), 1)
            keywords = [(word, count / total) for word, count in counts.most_common(self.top_k)]

        nodes: Dict[str, Dict[str, Any]] = {}
        for kw, weight in keywords:
            if len(kw) < 2:
                continue
            nodes[kw] = {
                "keyword": kw,
                "weight": round(weight, 3),
                "news_refs": 0,
                "sentiments": [],
            }
        return nodes

    def _match_keywords(
        self, title: str, keyword_nodes: Dict[str, Dict[str, Any]]
    ) -> List[str]:
        if not title or not keyword_nodes:
            return []
        return [kw for kw in keyword_nodes if kw in title]

    def _build_nodes(
        self,
        keyword_nodes: Dict[str, Dict[str, Any]],
        news_list: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        nodes: List[Dict[str, Any]] = []
        news_nodes = self._build_news_nodes(news_list, keyword_nodes)
        nodes.extend(news_nodes)

        sorted_kw = sorted(keyword_nodes.items(), key=lambda x: x[1]["news_refs"], reverse=True)
        existing_labels = {n["label"] for n in nodes}
        for kw, info in sorted_kw:
            if info["news_refs"] >= 2 and kw not in existing_labels:
                if len(nodes) >= self.top_k:
                    break
                sent_label = EventExtractor._dominant_sentiment(info["sentiments"])
                role = EventExtractor._classify_node_role(kw, f"关键词「{kw}」关联 {info['news_refs']} 条新闻")
                nodes.append({
                    "id": len(nodes) + 1,
                    "label": kw[:22],
                    "type": role,
                    "sentiment_type": sent_label,
                    "desc": f"关键词「{kw}」关联 {info['news_refs']} 条新闻",
                    "date": "",
                    "sentiment": {"positive": "正面", "negative": "负面", "neutral": "中性"}.get(sent_label, "中性"),
                    "strength": round(min(1.0, info["weight"]), 2),
                    "platform": "关键词提取",
                    "weight": max(1, info["news_refs"]),
                    "sources": [],
                    "source_refs": [],
                    "evidence_count": info["news_refs"],
                    "relevance_score": round(min(1.0, info["weight"]), 3),
                })
        return EventExtractor._assign_causal_layers(nodes)

    @staticmethod
    def _assign_causal_layers(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not nodes:
            return nodes
        sorted_nodes = sorted(nodes, key=lambda n: n.get("weight", 1), reverse=True)
        n = len(sorted_nodes)
        root_cut = max(1, min(3, n // 5))
        dev_cut = max(root_cut + 1, n * 3 // 5)
        for i, node in enumerate(sorted_nodes):
            if i < root_cut or node.get("weight", 1) >= 8:
                node["layer"] = 0
                node["is_root"] = True
                node["weight"] = max(node.get("weight", 1), 8)
            elif i < dev_cut or node.get("weight", 1) >= 5:
                node["layer"] = 1
                node["is_root"] = False
                node["weight"] = max(5, min(node.get("weight", 99), 7))
            else:
                node["layer"] = 2
                node["is_root"] = False
                node["weight"] = max(1, min(node.get("weight", 99), 4))
        return nodes

    def _build_news_nodes(
        self, news_list, keyword_nodes,
    ) -> List[Dict[str, Any]]:
        nodes: List[Dict[str, Any]] = []
        max_news_nodes = min(self.top_k, len(news_list))
        pos_news = [n for n in news_list if (n.get("sentiment_label") or "").lower() == "positive"]
        neg_news = [n for n in news_list if (n.get("sentiment_label") or "").lower() == "negative"]
        neu_news = [n for n in news_list if (n.get("sentiment_label") or "").lower() not in ("positive", "negative")]
        pos_news.sort(key=lambda n: abs(n.get("sentiment_score", 0)), reverse=True)
        neg_news.sort(key=lambda n: abs(n.get("sentiment_score", 0)), reverse=True)
        neu_news.sort(key=lambda n: abs(n.get("sentiment_score", 0)), reverse=True)
        neg_quota = max(3, max_news_nodes * 3 // 10)
        pos_quota = max_news_nodes * 35 // 100
        neu_quota = max_news_nodes - neg_quota - pos_quota
        sampled = []
        sampled.extend(neg_news[:neg_quota])
        sampled.extend(pos_news[:pos_quota])
        sampled.extend(neu_news[:neu_quota])
        if len(sampled) < max_news_nodes:
            remaining = [n for n in news_list if n not in sampled]
            remaining.sort(key=lambda n: abs(n.get("sentiment_score", 0)), reverse=True)
            sampled.extend(remaining[:max_news_nodes - len(sampled)])
        for i, news in enumerate(sampled[:max_news_nodes]):
            label = (news.get("sentiment_label") or "neutral").lower()
            sentiment_type = "pos" if label == "positive" else ("neg" if label == "negative" else "neu")
            title = (news.get("title") or f"新闻{i+1}")[:22]
            sentiment_score = news.get("sentiment_score", 0)
            for kw in self._match_keywords(news.get("title", ""), keyword_nodes):
                keyword_nodes[kw]["sentiments"].append(label)
            role = EventExtractor._classify_node_role(title, news.get("summary") or news.get("content") or "")
            source_refs = EventExtractor._news_source_refs(news)
            nodes.append({
                "id": i + 1,
                "label": title,
                "type": role,
                "sentiment_type": sentiment_type,
                "desc": (news.get("summary") or news.get("content") or "")[:100],
                "date": news.get("publish_time") or news.get("date") or "",
                "sentiment": "正面" if label == "positive" else "负面" if label == "negative" else "中性",
                "strength": round(abs(sentiment_score) if abs(sentiment_score) > 0.1 else 0.5, 2),
                "platform": (news.get("source") or news.get("platform") or "新闻媒体")[:20],
                "weight": max(1, int(abs(sentiment_score) * 10)),
                "sources": [{
                    "title": (news.get("title") or "")[:60],
                    "platform": (news.get("source") or news.get("platform") or "未知")[:20],
                    "time": news.get("publish_time") or news.get("date") or "",
                    "url": news.get("url") or news.get("link") or "",
                    "source_id": source_refs[0] if source_refs else "",
                }],
                "source_refs": source_refs,
                "evidence_count": max(1, len(source_refs)),
                "relevance_score": round(min(1.0, max(abs(sentiment_score), 0.1)), 3),
            })
        return nodes

    def _build_edges(
        self, nodes, news_list,
    ) -> List[Dict[str, Any]]:
        edges: List[Dict[str, Any]] = []
        edge_set = set()
        node_map = {n["id"]: n for n in nodes}
        adj = {n["id"]: set() for n in nodes}

        for news in news_list[:50]:
            title = news.get("title", "")
            if not title:
                continue
            words = set(EventExtractor._cut_words(title))
            matched_ids = []
            for node in nodes:
                if node["label"] in words or node["label"] in title:
                    matched_ids.append(node["id"])
            for a in range(len(matched_ids)):
                for b in range(a + 1, len(matched_ids)):
                    id_a, id_b = matched_ids[a], matched_ids[b]
                    key = (id_a, id_b)
                    if key not in edge_set:
                        edge_set.add(key)
                        na, nb = node_map[id_a], node_map[id_b]
                        la, lb = na.get("layer", 2), nb.get("layer", 2)
                        if la < lb:
                            rel_type, rel_label = "trigger", "触发"
                            frm, to = id_a, id_b
                        elif la > lb:
                            rel_type, rel_label = "cause", "引发"
                            frm, to = id_b, id_a
                        else:
                            rel_type, rel_label = "relate", "关联"
                            frm, to = id_a, id_b
                        signals = EventExtractor._relation_signals(na, nb)
                        aa = EventExtractor.adamic_adar_score(id_a, id_b, adj)
                        weight = abs(la - lb) + 1 + signals["score"] + aa * 1.5
                        edges.append({
                            "from": frm, "to": to,
                            "type": rel_type, "rel": rel_type,
                            "color": {"trigger": "#e74c3c", "cause": "#3498db", "relate": "#95a5a6", "escalate": "#e67e22"}.get(rel_type, "#95a5a6"),
                            "label": rel_label,
                            "weight": round(weight, 1),
                            "relation_signals": signals,
                            "adamic_adar": aa,
                            "relevance_score": round(signals["score"] + aa * 1.5, 1),
                        })
                        adj[frm].add(to)
                        adj[to].add(frm)

        # Root-to-root weak edges
        roots = [n for n in nodes if n.get("is_root")]
        for a in range(len(roots)):
            for b in range(a + 1, len(roots)):
                key = (roots[a]["id"], roots[b]["id"])
                if key not in edge_set:
                    edge_set.add(key)
                    signals = EventExtractor._relation_signals(roots[a], roots[b])
                    edges.append({
                        "from": roots[a]["id"], "to": roots[b]["id"],
                        "type": "weak", "rel": "weak",
                        "color": "#94a3b8", "label": "背景关联",
                        "weight": 1 + signals["score"],
                        "relation_signals": signals,
                        "relevance_score": signals["score"],
                    })

        # Ensure minimum edges
        if not edges and len(nodes) >= 2:
            for i in range(len(nodes) - 1):
                signals = EventExtractor._relation_signals(nodes[i], nodes[i + 1])
                edges.append({
                    "from": nodes[i]["id"], "to": nodes[i + 1]["id"],
                    "type": "relate", "rel": "relate",
                    "color": "#6366f1", "label": "关联",
                    "weight": 1 + signals["score"],
                    "relation_signals": signals,
                    "relevance_score": signals["score"],
                })

        return edges[: self.edge_k * 4]

    # ── Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _classify_node_role(label: str, desc: str = "") -> str:
        text = (label + " " + desc)
        if any(kw in text for kw in ["政策", "法规", "政府", "部门", "监管", "关税", "制裁", "法律", "谈判",
                                      "央行", "财政部", "商务部", "国务院", "行政", "立法"]):
            return "政策"
        if any(kw in text for kw in ["股市", "股价", "涨跌", "投资", "业绩", "营收", "财报", "利润",
                                      "市值", "IPO", "上市", "基金", "板块", "期货", "汇率"]):
            return "市场"
        if any(kw in text for kw in ["舆论", "网友", "热议", "争议", "口碑", "投诉", "曝光", "声量",
                                      "热搜", "刷屏", "吐槽", "维权", "抵制", "追捧"]):
            return "舆情"
        return "外部事件"

    @staticmethod
    def _dominant_sentiment(sentiments: List[str]) -> str:
        if not sentiments:
            return "neutral"
        counter = Counter(sentiments)
        most = counter.most_common(1)[0][0]
        return most if most in ("positive", "negative", "neutral") else "neutral"

    @staticmethod
    def _cut_words(text: str) -> List[str]:
        if jieba:
            return jieba.lcut(text)
        return re.findall(r'[一-龥]{2,}|[A-Za-z][A-Za-z0-9_-]+', text or "")

    @staticmethod
    def _news_source_refs(news: Dict[str, Any]) -> List[str]:
        refs = news.get("source_refs") or []
        if isinstance(refs, list):
            return [str(ref) for ref in refs if ref]
        if isinstance(refs, str) and refs:
            return [refs]
        source_ref = news.get("source_ref") or {}
        sid = source_ref.get("source_id") if isinstance(source_ref, dict) else ""
        return [sid] if sid else []

    @staticmethod
    def _relation_signals(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
        left_refs = set(left.get("source_refs") or [])
        right_refs = set(right.get("source_refs") or [])
        shared_source = bool(left_refs & right_refs)
        left_plat = str(left.get("platform") or "")
        right_plat = str(right.get("platform") or "")
        same_platform = bool(left_plat and left_plat == right_plat)
        left_sent = left.get("sentiment_type") or ""
        right_sent = right.get("sentiment_type") or ""
        sentiment_alignment = bool(left_sent and left_sent == right_sent)
        sentiment_opposition = {left_sent, right_sent} == {"pos", "neg"}
        left_date = str(left.get("date") or "")[:10]
        right_date = str(right.get("date") or "")[:10]
        same_day = bool(left_date and right_date and left_date == right_date)
        left_type = str(left.get("type") or "")
        right_type = str(right.get("type") or "")
        type_affinity = bool(left_type and left_type == right_type)
        score = 0.0
        if shared_source:
            score += 4.0
        if sentiment_opposition:
            score += 3.0
        if same_platform:
            score += 2.0
        if sentiment_alignment:
            score += 1.0
        if type_affinity:
            score += 1.0
        if same_day:
            score += 1.0
        return {
            "shared_source": shared_source,
            "same_platform": same_platform,
            "same_day": same_day,
            "sentiment_alignment": sentiment_alignment,
            "sentiment_opposition": sentiment_opposition,
            "type_affinity": type_affinity,
            "score": round(score, 1),
        }

    @staticmethod
    def adamic_adar_score(left_id: int, right_id: int, adj: dict) -> float:
        left_neighbors = adj.get(left_id, set())
        right_neighbors = adj.get(right_id, set())
        shared = left_neighbors & right_neighbors
        if not shared:
            return 0.0
        total = 0.0
        for neighbor in shared:
            deg = len(adj.get(neighbor, set()))
            total += 1.0 / (deg).bit_length() if deg > 1 else 1.0
        return round(total, 3)
