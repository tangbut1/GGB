import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.collect.ingest_cache import IngestCache


_SAMPLE = [{"title": "华为发布新AI芯片", "summary": "重大技术突破"}]


def test_ingest_cache_put_and_get():
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = IngestCache(tmpdir, ttl_seconds=999)
        cache.put("华为", "news", _SAMPLE)
        assert cache.has("华为", "news")
        result = cache.get("华为", "news")
        assert len(result) == 1
        assert result[0]["title"] == "华为发布新AI芯片"


def test_ingest_cache_miss_for_unknown_keyword():
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = IngestCache(tmpdir, ttl_seconds=999)
        assert not cache.has("unknown", "news")


def test_ingest_cache_hash_stability():
    a = IngestCache.hash_news([{"title": "A"}, {"title": "B"}])
    b = IngestCache.hash_news([{"title": "A"}, {"title": "B"}])
    assert a == b


def test_ingest_cache_hash_differs():
    a = IngestCache.hash_news([{"title": "A"}])
    b = IngestCache.hash_news([{"title": "B"}])
    assert a != b


def test_ingest_cache_expiry():
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = IngestCache(tmpdir, ttl_seconds=0)
        cache.put("华为", "news", _SAMPLE)
        assert not cache.has("华为", "news")
        assert cache.get("华为", "news") is None
