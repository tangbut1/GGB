import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analysis.event_extractor import EventExtractor


def test_event_graph_nodes_include_source_evidence_metadata():
    analyzed_news = [
        {
            "title": "华为供应链订单增长",
            "summary": "供应链订单增长推动市场预期。",
            "source": "财新",
            "publish_time": "2026-05-23 09:30",
            "sentiment_label": "positive",
            "sentiment_score": 0.7,
            "source_refs": ["src_a"],
        },
        {
            "title": "华为供应链交付风险升温",
            "summary": "供应链交付存在短期扰动。",
            "source": "财新",
            "publish_time": "2026-05-23 10:00",
            "sentiment_label": "negative",
            "sentiment_score": -0.6,
            "source_refs": ["src_b"],
        },
    ]

    result = EventExtractor(top_k=6, edge_k=4).extract_events(analyzed_news)

    assert result["nodes"]
    for node in result["nodes"]:
        assert "source_refs" in node
        assert "evidence_count" in node
        assert "relevance_score" in node


def test_event_graph_edges_include_relation_signals():
    analyzed_news = [
        {
            "title": "华为供应链订单增长",
            "summary": "供应链订单增长推动市场预期。",
            "source": "财新",
            "publish_time": "2026-05-23 09:30",
            "sentiment_label": "positive",
            "sentiment_score": 0.7,
            "source_refs": ["src_shared"],
        },
        {
            "title": "华为供应链交付风险升温",
            "summary": "供应链交付存在短期扰动。",
            "source": "财新",
            "publish_time": "2026-05-23 10:00",
            "sentiment_label": "negative",
            "sentiment_score": -0.6,
            "source_refs": ["src_shared"],
        },
    ]

    result = EventExtractor(top_k=6, edge_k=4).extract_events(analyzed_news)

    assert result["edges"]
    assert "relation_signals" in result["edges"][0]
    assert "shared_source" in result["edges"][0]["relation_signals"]


if __name__ == "__main__":
    test_event_graph_nodes_include_source_evidence_metadata()
    test_event_graph_edges_include_relation_signals()
