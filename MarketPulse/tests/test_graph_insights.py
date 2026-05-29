import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.knowledge.graph_insights import analyze_graph


def _sample_graph():
    """Build a realistic event graph with 8 nodes across 3 causal layers."""
    nodes = [
        {"id": 1, "label": "华为发布新AI芯片", "type": "市场", "sentiment": "正面",
         "sentiment_type": "pos", "layer": 0, "weight": 9,
         "source_refs": ["src_a"], "platform": "证券时报"},
        {"id": 2, "label": "竞争对手宣布降价", "type": "市场", "sentiment": "负面",
         "sentiment_type": "neg", "layer": 0, "weight": 8,
         "source_refs": ["src_b"], "platform": "财新"},
        {"id": 3, "label": "芯片供应链紧张加剧", "type": "外部事件", "sentiment": "负面",
         "sentiment_type": "neg", "layer": 1, "weight": 6,
         "source_refs": ["src_c", "src_a"], "platform": "Reuters"},
        {"id": 4, "label": "投资者情绪分化明显", "type": "舆情", "sentiment": "中性",
         "sentiment_type": "neu", "layer": 1, "weight": 5,
         "source_refs": ["src_d"], "platform": "微博"},
        {"id": 5, "label": "相关板块股价大幅波动", "type": "市场", "sentiment": "负面",
         "sentiment_type": "neg", "layer": 2, "weight": 4,
         "source_refs": ["src_e"], "platform": "东方财富"},
        {"id": 6, "label": "分析师上调预期", "type": "市场", "sentiment": "正面",
         "sentiment_type": "pos", "layer": 2, "weight": 3,
         "source_refs": ["src_f"], "platform": "证券时报"},
        {"id": 7, "label": "孤立的监管公告", "type": "政策", "sentiment": "中性",
         "sentiment_type": "neu", "layer": 0, "weight": 2,
         "source_refs": ["src_g"], "platform": "政府网站"},
        {"id": 8, "label": "孤立的专利新闻", "type": "外部事件", "sentiment": "中性",
         "sentiment_type": "neu", "layer": 0, "weight": 1,
         "source_refs": ["src_h"], "platform": "知识产权报"},
    ]

    edges = [
        {"from": 1, "to": 3, "type": "trigger", "weight": 4, "relation_signals": {"score": 4, "shared_source": True, "same_platform": False, "same_day": True, "sentiment_alignment": False}},
        {"from": 2, "to": 5, "type": "trigger", "weight": 4, "relation_signals": {"score": 2, "shared_source": False, "same_platform": False, "same_day": True, "sentiment_alignment": True}},
        {"from": 3, "to": 5, "type": "cause",  "weight": 3, "relation_signals": {"score": 2, "shared_source": False, "same_platform": False, "same_day": True, "sentiment_alignment": True}},
        {"from": 1, "to": 6, "type": "relate", "weight": 2, "relation_signals": {"score": 2, "shared_source": False, "same_platform": True, "same_day": False, "sentiment_alignment": True}},
        {"from": 4, "to": 5, "type": "relate", "weight": 2, "relation_signals": {"score": 1, "shared_source": False, "same_platform": False, "same_day": True, "sentiment_alignment": False}},
        {"from": 7, "to": 1, "type": "weak",  "weight": 1, "relation_signals": {"score": 0, "shared_source": False, "same_platform": False, "same_day": False, "sentiment_alignment": False}},
    ]

    return nodes, edges


def test_graph_insights_detects_surprising_connections():
    nodes, edges = _sample_graph()
    result = analyze_graph(nodes, edges)

    connections = result["surprising_connections"]
    assert len(connections) >= 2, f"Expected ≥2 surprising connections, got {len(connections)}"

    # Should include the cross-sentiment edge (pos node 1 → neg node 3)
    labels = {c["source"]["label"] for c in connections} | {c["target"]["label"] for c in connections}
    assert any("AI芯片" in l for l in labels) or any("供应链" in l for l in labels)


def test_graph_insights_detects_isolated_nodes():
    nodes, edges = _sample_graph()
    # Node 8 is truly isolated (0 edges)
    result = analyze_graph(nodes, edges)

    gaps = result["knowledge_gaps"]
    isolated = [g for g in gaps if g["type"] == "isolated"]
    assert len(isolated) >= 1, f"Expected ≥1 isolated node, got {len(isolated)}"

    isolated_labels = {g["title"] for g in isolated}
    assert any("专利" in l for l in isolated_labels), f"Node 8 (专利) should appear as isolated, got {isolated_labels}"


def test_graph_insights_returns_community_summary():
    nodes, edges = _sample_graph()
    result = analyze_graph(nodes, edges)

    communities = result["communities"]
    assert len(communities) >= 1, f"Expected ≥1 community, got {len(communities)}"

    for c in communities:
        assert "size" in c
        assert "dominant_sentiment" in c
        assert c["size"] >= 2, f"Community {c['community_id']} too small ({c['size']})"


def test_graph_insights_graph_stats():
    nodes, edges = _sample_graph()
    result = analyze_graph(nodes, edges)

    stats = result["graph_stats"]
    assert stats["node_count"] == 8
    assert stats["edge_count"] == 6
    assert stats["density"] > 0
    assert stats["avg_degree"] > 0


def test_graph_insights_handles_empty_graph():
    result = analyze_graph([], [])
    assert result["graph_stats"]["node_count"] == 0
    assert result["surprising_connections"] == []
    assert result["knowledge_gaps"] == []
    assert result["communities"] == []


def test_graph_insights_detects_bridge_nodes():
    """A node connecting otherwise-disconnected clusters should be flagged."""
    nodes = [
        {"id": 1, "label": "Bridge Event", "type": "舆情", "sentiment": "中性", "sentiment_type": "neu", "layer": 1, "weight": 5, "source_refs": ["src_x"], "platform": "综合"},
        {"id": 2, "label": "Policy A", "type": "政策", "sentiment": "正面", "sentiment_type": "pos", "layer": 0, "weight": 3, "source_refs": ["src_a"], "platform": "政务"},
        {"id": 3, "label": "Policy B", "type": "政策", "sentiment": "正面", "sentiment_type": "pos", "layer": 0, "weight": 3, "source_refs": ["src_a"], "platform": "政务"},
        {"id": 4, "label": "Market A", "type": "市场", "sentiment": "负面", "sentiment_type": "neg", "layer": 2, "weight": 4, "source_refs": ["src_b"], "platform": "财经"},
        {"id": 5, "label": "Market B", "type": "市场", "sentiment": "负面", "sentiment_type": "neg", "layer": 2, "weight": 4, "source_refs": ["src_b"], "platform": "财经"},
        {"id": 6, "label": "External A", "type": "外部事件", "sentiment": "中性", "sentiment_type": "neu", "layer": 0, "weight": 3, "source_refs": ["src_c"], "platform": "国际"},
        {"id": 7, "label": "External B", "type": "外部事件", "sentiment": "中性", "sentiment_type": "neu", "layer": 0, "weight": 3, "source_refs": ["src_c"], "platform": "国际"},
    ]
    # Three dense clusters (policy, market, external), only connected via node 1
    edges = [
        {"from": 1, "to": 2, "type": "relate", "weight": 1, "relation_signals": {"score": 0}},
        {"from": 1, "to": 4, "type": "relate", "weight": 1, "relation_signals": {"score": 0}},
        {"from": 1, "to": 6, "type": "relate", "weight": 1, "relation_signals": {"score": 0}},
        # Intra-cluster edges
        {"from": 2, "to": 3, "type": "relate", "weight": 3, "relation_signals": {"score": 4, "shared_source": True}},
        {"from": 4, "to": 5, "type": "relate", "weight": 3, "relation_signals": {"score": 4, "shared_source": True}},
        {"from": 6, "to": 7, "type": "relate", "weight": 3, "relation_signals": {"score": 4, "shared_source": True}},
    ]

    result = analyze_graph(nodes, edges)
    bridges = [g for g in result["knowledge_gaps"] if g["type"] == "bridge"]
    assert len(bridges) >= 1, f"Node 1 should be bridge, got bridges: {bridges}"
    # Verify node 1 is the bridge
    bridge_node_ids = [b["node_id"] for b in bridges]
    assert 1 in bridge_node_ids, f"Expected node 1 as bridge, got {bridge_node_ids}"
