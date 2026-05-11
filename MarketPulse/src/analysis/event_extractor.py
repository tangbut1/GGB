import re
from collections import Counter
from typing import Any, Dict, List

import jieba
import jieba.analyse


class EventExtractor:
    """从已分析新闻中提取关键事件并构建关系图谱。

    输出格式对齐前端 mergeBackendData() 的 nodes / edges 结构。
    """

    def __init__(self, top_k: int = 20, edge_k: int = 12):
        self.top_k = top_k
        self.edge_k = edge_k

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def extract_events(
        self, analyzed_news: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """主入口：输入已做情感分析的新闻列表，输出 nodes + edges。"""
        if not analyzed_news:
            return {"nodes": [], "edges": []}

        # 1. 提取关键词作为事件节点候选
        keyword_nodes = self._extract_keyword_nodes(analyzed_news)

        # 2. 将每条新闻映射到最相关的关键词节点
        for news in analyzed_news:
            if not isinstance(news, dict):
                continue
            title = news.get("title", "")
            matched = self._match_keywords(title, keyword_nodes)
            for kw in matched:
                keyword_nodes[kw]["news_refs"] += 1

        # 3. 构建最终节点列表（过滤掉单条引用的噪声节点）
        nodes = self._build_nodes(keyword_nodes, analyzed_news)

        # 4. 构建边（基于关键词共现）
        edges = self._build_edges(nodes, analyzed_news)

        return {"nodes": nodes, "edges": edges}

    # ------------------------------------------------------------------
    # Keyword extraction
    # ------------------------------------------------------------------
    def _extract_keyword_nodes(
        self, news_list: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """用 jieba TF-IDF 从所有标题中提取关键词作为事件节点候选。"""
        all_titles = []
        for news in news_list:
            title = news.get("title", "")
            if title and isinstance(title, str):
                all_titles.append(title)

        if not all_titles:
            return {}

        combined = "。".join(all_titles)
        keywords = jieba.analyse.extract_tags(combined, topK=self.top_k, withWeight=True)

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
        """返回标题中命中的关键词列表。"""
        if not title or not keyword_nodes:
            return []
        matched = []
        for kw in keyword_nodes:
            if kw in title:
                matched.append(kw)
        return matched

    # ------------------------------------------------------------------
    # Build nodes (with causal layer assignment)
    # ------------------------------------------------------------------
    def _build_nodes(
        self,
        keyword_nodes: Dict[str, Dict[str, Any]],
        news_list: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """将关键词节点转为前端 nodes 格式，按因果层级分配 layer。"""
        nodes: List[Dict[str, Any]] = []

        # 基于真实新闻生成事件节点
        news_nodes = self._build_news_nodes(news_list, keyword_nodes)
        nodes.extend(news_nodes)

        # 从关键词中补充被引用次数高的 TOP 节点
        sorted_kw = sorted(
            keyword_nodes.items(),
            key=lambda x: x[1]["news_refs"],
            reverse=True,
        )
        existing_labels = {n["label"] for n in nodes}
        for kw, info in sorted_kw:
            if info["news_refs"] >= 2 and kw not in existing_labels:
                if len(nodes) >= self.top_k:
                    break
                sent_label = self._dominant_sentiment(info["sentiments"])
                role = self._classify_node_role(kw, f"关键词「{kw}」关联 {info['news_refs']} 条新闻")
                nodes.append(
                    {
                        "id": len(nodes) + 1,
                        "label": kw[:22],
                        "type": role,
                        "sentiment_type": sent_label,
                        "desc": f"关键词「{kw}」关联 {info['news_refs']} 条新闻",
                        "date": "",
                        "sentiment": {
                            "positive": "正面",
                            "negative": "负面",
                            "neutral": "中性",
                        }.get(sent_label, "中性"),
                        "strength": round(min(1.0, info["weight"]), 2),
                        "platform": "关键词提取",
                        "weight": max(1, info["news_refs"]),
                        "sources": [],
                    }
                )

        # ── 因果层级分配 ──
        nodes = self._assign_causal_layers(nodes)

        return nodes

    @staticmethod
    def _assign_causal_layers(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """按权重大小和情感极端度分配因果层级。
        level 0（根节点/起因）：weight≥8 或最高 weight 的 top 20%
        level 1（发展节点/经过）：weight 5~7 或中间 40%
        level 2（末端节点/影响）：weight 1~4 或最低 40%
        """
        if not nodes:
            return nodes

        sorted_nodes = sorted(nodes, key=lambda n: n.get("weight", 1), reverse=True)
        n = len(sorted_nodes)
        root_cut = max(1, min(3, n // 5))       # top 20%, at least 1, max 3
        dev_cut = max(root_cut + 1, n * 3 // 5)  # middle 40%

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
        self,
        news_list: List[Dict[str, Any]],
        keyword_nodes: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """从真实新闻列表生成节点（取有代表性的前 N 条）。"""
        nodes: List[Dict[str, Any]] = []
        max_news_nodes = min(self.top_k, len(news_list))

        # ── 分层采样：确保正/负/中性节点都有代表，避免正面绝对值碾压负面 ──
        pos_news = [n for n in news_list if (n.get("sentiment_label") or "").lower() == "positive"]
        neg_news = [n for n in news_list if (n.get("sentiment_label") or "").lower() == "negative"]
        neu_news = [n for n in news_list if (n.get("sentiment_label") or "").lower() not in ("positive", "negative")]

        # 按各自的情感得分绝对值排序（组内按极端度）
        pos_news.sort(key=lambda n: abs(n.get("sentiment_score", 0)), reverse=True)
        neg_news.sort(key=lambda n: abs(n.get("sentiment_score", 0)), reverse=True)
        neu_news.sort(key=lambda n: abs(n.get("sentiment_score", 0)), reverse=True)

        # 配额：负面至少 30%，正面 35%，中性 35%
        neg_quota = max(3, max_news_nodes * 3 // 10)   # 最少 3 个负面
        pos_quota = max_news_nodes * 35 // 100
        neu_quota = max_news_nodes - neg_quota - pos_quota

        sampled = []
        sampled.extend(neg_news[:neg_quota])
        sampled.extend(pos_news[:pos_quota])
        sampled.extend(neu_news[:neu_quota])

        # 如果某类不足，用其他类补充
        if len(sampled) < max_news_nodes:
            remaining = [n for n in news_list if n not in sampled]
            remaining.sort(key=lambda n: abs(n.get("sentiment_score", 0)), reverse=True)
            sampled.extend(remaining[:max_news_nodes - len(sampled)])

        for i, news in enumerate(sampled[:max_news_nodes]):
            label = (news.get("sentiment_label") or "neutral").lower()
            sentiment_type = "pos" if label == "positive" else ("neg" if label == "negative" else "neu")

            title = (news.get("title") or f"新闻{i+1}")[:22]
            sentiment_score = news.get("sentiment_score", 0)

            # 把命中的关键词记录到 keyword_nodes 的情感分布中
            for kw in self._match_keywords(news.get("title", ""), keyword_nodes):
                keyword_nodes[kw]["sentiments"].append(label)

            role = self._classify_node_role(title, news.get("summary") or news.get("content") or "")

            nodes.append(
                {
                    "id": i + 1,
                    "label": title,
                    "type": role,
                    "sentiment_type": sentiment_type,
                    "desc": (news.get("summary") or news.get("content") or "")[:100],
                    "date": news.get("publish_time") or news.get("date") or "",
                    "sentiment": (
                        "正面" if label == "positive" else "负面" if label == "negative" else "中性"
                    ),
                    "strength": round(abs(sentiment_score) if abs(sentiment_score) > 0.1 else 0.5, 2),
                    "platform": (news.get("source") or news.get("platform") or "新闻媒体")[:20],
                    "weight": max(1, int(abs(sentiment_score) * 10)),
                    "sources": [{
                        "title": (news.get("title") or "")[:60],
                        "platform": (news.get("source") or news.get("platform") or "未知")[:20],
                        "time": news.get("publish_time") or news.get("date") or "",
                        "url": news.get("url") or news.get("link") or "",
                    }],
                }
            )
        return nodes

    # ------------------------------------------------------------------
    # Build edges (with directional causality)
    # ------------------------------------------------------------------
    def _build_edges(
        self,
        nodes: List[Dict[str, Any]],
        news_list: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """基于节点层级和关键词共现构建有向因果边。"""
        edges: List[Dict[str, Any]] = []
        edge_set = set()
        node_map = {n["id"]: n for n in nodes}

        # 辅助函数：确定两节点间的边类型
        def _edge_relation(n_from, n_to):
            lf = n_from.get("layer", 2)
            lt = n_to.get("layer", 2)
            if lf < lt:
                return "trigger", "触发"
            if lf > lt:
                return "cause", "引发"
            return "relate", "关联"

        # 同一条新闻中命中的节点之间建立关系
        for news in news_list[:50]:
            title = news.get("title", "")
            if not title:
                continue
            words = set(jieba.lcut(title))
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
                        # 从高层级指向低层级
                        if la < lb:
                            rel_type, rel_label = "trigger", "触发"
                            frm, to = id_a, id_b
                        elif la > lb:
                            rel_type, rel_label = "cause", "引发"
                            frm, to = id_b, id_a
                        else:
                            rel_type, rel_label = "relate", "关联"
                            frm, to = id_a, id_b
                        edges.append({
                            "from": frm, "to": to,
                            "type": rel_type, "rel": rel_type,
                            "color": {"trigger": "#e74c3c", "cause": "#3498db", "relate": "#95a5a6", "escalate": "#e67e22"}.get(rel_type, "#95a5a6"),
                            "label": rel_label,
                            "weight": abs(la - lb) + 1,
                        })

        # 根节点之间：弱关联
        roots = [n for n in nodes if n.get("is_root")]
        for a in range(len(roots)):
            for b in range(a + 1, len(roots)):
                key = (roots[a]["id"], roots[b]["id"])
                if key not in edge_set:
                    edge_set.add(key)
                    edges.append({
                        "from": roots[a]["id"], "to": roots[b]["id"],
                        "type": "weak", "rel": "weak",
                        "color": "#94a3b8", "label": "背景关联",
                        "weight": 1,
                    })

        # 确保最少边 + 触发类边 ≥ 40%
        total_edges = len(edges)
        trigger_edges = sum(1 for e in edges if e["type"] in ("trigger", "cause", "escalate"))
        if total_edges > 0 and trigger_edges / total_edges < 0.4:
            # 补充跨层边
            layer0_nodes = [n for n in nodes if n.get("layer") == 0]
            layer1_nodes = [n for n in nodes if n.get("layer") == 1]
            layer2_nodes = [n for n in nodes if n.get("layer") == 2]
            for l0 in layer0_nodes[:3]:
                for l1 in layer1_nodes[:5]:
                    key = (l0["id"], l1["id"])
                    if key not in edge_set:
                        edge_set.add(key)
                        edges.append({
                            "from": l0["id"], "to": l1["id"],
                            "type": "trigger", "rel": "trigger",
                            "color": "#e74c3c", "label": "触发",
                            "weight": 3,
                        })
            for l0 in layer0_nodes[:2]:
                for l2 in layer2_nodes[:3]:
                    key = (l0["id"], l2["id"])
                    if key not in edge_set:
                        edge_set.add(key)
                        edges.append({
                            "from": l0["id"], "to": l2["id"],
                            "type": "escalate", "rel": "escalate",
                            "color": "#e67e22", "label": "激化",
                            "weight": 3,
                        })

        if not edges and len(nodes) >= 2:
            for i in range(len(nodes) - 1):
                edges.append({
                    "from": nodes[i]["id"], "to": nodes[i + 1]["id"],
                    "type": "relate", "rel": "relate",
                    "color": "#6366f1", "label": "关联",
                    "weight": 1,
                })

        return edges[: self.edge_k * 4]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _classify_node_role(label: str, desc: str = "") -> str:
        """按语义关键词将节点归类为：政策 / 市场 / 舆情 / 外部事件"""
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
