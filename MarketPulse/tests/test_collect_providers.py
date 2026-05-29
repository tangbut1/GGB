import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.collect.providers import annotate_source_refs


def test_annotate_source_refs_adds_stable_evidence_fields():
    records = [
        {
            "title": "华为发布新产品",
            "summary": "新品发布带动供应链关注。",
            "link": "https://finance.example.com/news/123?from=rss",
            "source": "Example Finance",
            "publish_time": "2026-05-23 09:30",
        }
    ]

    annotated, sources = annotate_source_refs(
        records,
        collected_at="2026-05-23T10:00:00",
    )

    assert len(annotated) == 1
    assert len(sources) == 1

    item = annotated[0]
    source = sources[0]

    assert item["url"] == "https://finance.example.com/news/123?from=rss"
    assert item["link"] == item["url"]
    assert item["domain"] == "finance.example.com"
    assert item["content_hash"] == source["content_hash"]
    assert len(item["content_hash"]) == 64
    assert item["source_refs"] == [source["source_id"]]
    assert item["source_ref"]["source_id"] == source["source_id"]
    assert item["source_ref"]["title"] == "华为发布新产品"
    assert source["collected_at"] == "2026-05-23T10:00:00"


def test_annotate_source_refs_deduplicates_by_url():
    records = [
        {"title": "同一新闻 A", "link": "https://example.com/a", "summary": "first"},
        {"title": "同一新闻 B", "url": "https://example.com/a", "summary": "second"},
    ]

    annotated, sources = annotate_source_refs(records, collected_at="2026-05-23T10:00:00")

    assert len(annotated) == 2
    assert len(sources) == 1
    assert annotated[0]["source_refs"] == annotated[1]["source_refs"]


if __name__ == "__main__":
    test_annotate_source_refs_adds_stable_evidence_fields()
    test_annotate_source_refs_deduplicates_by_url()
