"""多维舆情指标测试。

锁住三件事：
1. 每个维度的值都由样本算出，不引入外部基准、插值或占位；
2. 样本不足时维度带 ``sufficient=False``，而不是给一个看着像有数据的数；
3. 无日期、无打分、空输入都不抛异常——采集端给什么就得能算什么。
"""

import pytest

from src.analysis.sentiment_indicators import compute_indicators, daily_series


def _item(score=None, label=None, tier=2, day=None, domain="a.com"):
    item = {
        "title": "t",
        "source": "某来源",
        "source_domain": domain,
        "source_tier": tier,
        "publish_time": f"{day} 10:00:00" if day else "",
    }
    if score is not None:
        item["sentiment_score"] = score
        item["sentiment_label"] = label
    return item


def test_empty_input_returns_empty_dimensions():
    out = compute_indicators([])
    assert out["dimensions"] == []
    assert out["daily"] == []
    assert out["sample"]["total"] == 0


def test_non_dict_entries_are_skipped():
    out = compute_indicators([None, "x", 3, _item(score=-0.8, label="negative")])
    assert out["sample"]["total"] == 1


def test_sentiment_index_is_mean_of_scores_mapped_to_0_100():
    # 均值 0 → 归一化 50；均值 -1 → 0；均值 1 → 100
    news = [_item(score=0.0, label="neutral", day="2026-09-01", domain=f"d{i}.com")
            for i in range(6)]
    dim = {d["key"]: d for d in compute_indicators(news)["dimensions"]}["sentiment_index"]
    assert dim["value"] == 50.0

    news = [_item(score=-1.0, label="negative", day="2026-09-01", domain=f"d{i}.com")
            for i in range(6)]
    dim = {d["key"]: d for d in compute_indicators(news)["dimensions"]}["sentiment_index"]
    assert dim["value"] == 0.0


def test_negative_share_uses_labels_not_score_threshold():
    news = [
        _item(score=-0.2, label="negative", day="2026-09-01", domain="a.com"),
        _item(score=-0.1, label="negative", day="2026-09-01", domain="b.com"),
        _item(score=0.1, label="positive", day="2026-09-01", domain="c.com"),
        _item(score=0.0, label="neutral", day="2026-09-01", domain="d.com"),
    ]
    dim = {d["key"]: d for d in compute_indicators(news)["dimensions"]}["negative_share"]
    assert dim["value"] == 50.0
    assert "2/4" in dim["display"]


def test_polarization_counts_extreme_scores_only():
    news = [
        _item(score=-0.8, label="negative", day="2026-09-01", domain="a.com"),
        _item(score=0.9, label="positive", day="2026-09-01", domain="b.com"),
        _item(score=0.2, label="positive", day="2026-09-01", domain="c.com"),
        _item(score=-0.3, label="negative", day="2026-09-01", domain="d.com"),
    ]
    dim = {d["key"]: d for d in compute_indicators(news)["dimensions"]}["polarization"]
    assert dim["value"] == 50.0
    assert dim["raw"] == 2


def test_source_diversity_penalises_single_dominant_domain():
    # 同一站点 9 条 + 别处 1 条：来源数是 2，但集中度接近单一站点，
    # 1 - HHI 应给出很低的分数（归一化香农熵在这里会给出 47，读着像中等多元）
    news = ([_item(score=0.0, label="neutral", day="2026-09-01", domain="spam.com")] * 9
            + [_item(score=0.0, label="neutral", day="2026-09-01", domain="other.com")])
    dim = {d["key"]: d for d in compute_indicators(news)["dimensions"]}["source_diversity"]
    assert dim["value"] < 20.0
    assert "1 - Σ(占比²)" in dim["basis"]


def test_source_diversity_is_zero_for_single_domain():
    news = [_item(score=0.0, label="neutral", day="2026-09-01", domain="only.com") for _ in range(5)]
    dim = {d["key"]: d for d in compute_indicators(news)["dimensions"]}["source_diversity"]
    assert dim["value"] == 0.0


def test_authority_share_counts_tier_le_1():
    news = [
        _item(score=0.0, label="neutral", tier=1, day="2026-09-01", domain="a.com"),
        _item(score=0.0, label="neutral", tier=2, day="2026-09-01", domain="b.com"),
        _item(score=0.0, label="neutral", tier=4, day="2026-09-01", domain="c.com"),
        _item(score=0.0, label="neutral", tier=3, day="2026-09-01", domain="d.com"),
    ]
    dims = {d["key"]: d for d in compute_indicators(news)["dimensions"]}
    assert dims["authority_share"]["value"] == 25.0
    assert dims["low_credibility_share"]["value"] == 25.0


def test_insufficient_samples_are_flagged_not_faked():
    # 只有 2 条：声量/多样性/日期覆盖的 sufficient 必须为 False
    news = [_item(score=-0.5, label="negative", day="2026-09-01", domain="a.com"),
            _item(score=-0.4, label="negative", day="2026-09-02", domain="b.com")]
    dims = {d["key"]: d for d in compute_indicators(news)["dimensions"]}
    assert dims["volume"]["sufficient"] is False
    assert dims["source_diversity"]["sufficient"] is False
    # 情绪指数和负面占比有 2 条也能算，但仍低于 5 条门槛
    assert dims["sentiment_index"]["sufficient"] is False


def test_daily_series_groups_by_date_and_keeps_undated():
    news = [
        _item(score=-0.6, label="negative", tier=1, day="2026-09-02", domain="a.com"),
        _item(score=0.4, label="positive", tier=2, day="2026-09-02", domain="b.com"),
        _item(score=-0.2, label="negative", tier=1, day="2026-09-01", domain="c.com"),
        _item(score=0.0, label="neutral", day="", domain="d.com"),
    ]
    series = daily_series(news)
    assert [d["date"] for d in series] == ["2026-09-01", "2026-09-02", "unknown"]
    assert series[1]["volume"] == 2
    assert series[1]["negative_share"] == 50.0
    assert series[1]["t1_share"] == 50.0
    # 无日期的一组不丢，但单独归类而不是摊到某一天
    assert series[2]["volume"] == 1
    assert series[2]["date"] == "unknown"


def test_attention_burst_is_peak_over_daily_mean():
    news = ([_item(score=0.0, label="neutral", day="2026-09-01", domain=f"a{i}.com") for i in range(10)]
            + [_item(score=0.0, label="neutral", day="2026-09-02", domain=f"b{i}.com") for i in range(1)])
    dim = {d["key"]: d for d in compute_indicators(news)["dimensions"]}["attention_burst"]
    # 峰值 10 / 日均 5.5 ≈ 1.82
    assert dim["raw"] == pytest.approx(1.82, abs=0.01)
    assert dim["sufficient"] is True


def test_attention_burst_marks_insufficient_with_one_day():
    news = [_item(score=0.0, label="neutral", day="2026-09-01", domain=f"a{i}.com") for i in range(6)]
    dim = {d["key"]: d for d in compute_indicators(news)["dimensions"]}["attention_burst"]
    assert dim["sufficient"] is False


def test_every_dimension_carries_basis_and_hint():
    news = [_item(score=-0.5, label="negative", day="2026-09-01", domain=f"a{i}.com") for i in range(6)]
    for d in compute_indicators(news)["dimensions"]:
        assert d["basis"], f"{d['key']} 缺少计算依据"
        assert d["hint"], f"{d['key']} 缺少口径说明"
        assert d["value"] is None or 0 <= d["value"] <= 100, f"{d['key']} 归一化值越界"
        assert d["display"]


def test_missing_scores_do_not_crash_sentiment_index():
    news = [_item(day="2026-09-01", domain=f"a{i}.com") for i in range(6)]
    dims = {d["key"]: d for d in compute_indicators(news)["dimensions"]}
    # 一条都没打分时必须是 None。0 分归一化后正好是 50 = "完全中性"，
    # 那等于把"没有数据"显示成"数据说中性"。
    assert dims["sentiment_index"]["value"] is None
    assert dims["sentiment_index"]["display"] == "无打分样本"
    assert dims["sentiment_index"]["sufficient"] is False
    assert dims["polarization"]["value"] is None
    assert dims["polarization"]["display"] == "无打分样本"
