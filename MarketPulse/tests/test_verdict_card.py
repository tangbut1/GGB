"""研判卡测试。

锁住的核心约定：
1. **风险分与趋势方向是确定性计算**——同一批指标喂进去必须得到同一个
   等级，不随模型措辞变化。这是卡上"怎么算的"可被用户复算的前提。
2. **样本不足必须显式降级**——低置信标记、watch_items 里的提示，而不是
   拿 6 条样本撑出一个"高风险"。
3. **没有伪造数据**——空指标、无日期、无打分都不抛异常，缺就说缺。
"""

import pytest

from src.analysis.sentiment_indicators import compute_indicators
from src.analysis.verdict_card import (
    build_verdict_card, core_evidence, observation_window,
    risk_level, risk_score, trend_direction, watch_items,
)


def _news(n, *, tier=2, day=None, label="negative", domain="a.com"):
    return {
        "title": f"标题 {n}",
        "source": f"来源 {n}",
        "source_domain": domain,
        "source_tier": tier,
        "publish_time": f"{day} 10:00:00" if day else "",
        "sentiment_score": -0.7 if label == "negative" else 0.6,
        "sentiment_label": label,
        "url": f"https://{domain}/a{n}",
    }


def _indicators(**overrides):
    base = {
        "dimensions": [
            {"key": "negative_share", "value": 60.0},
            {"key": "attention_burst", "value": 70.0},
            {"key": "low_credibility_share", "value": 30.0},
            {"key": "authority_share", "value": 10.0},
            {"key": "sentiment_index", "value": 30.0},
        ],
        "sample": {"total": 50, "known_days": 7, "tier1": 5, "tier4": 15, "undated": 0},
        "daily": [],
    }
    base.update(overrides)
    return base


# ── 风险分 ────────────────────────────────────────────────────────

def test_risk_score_is_weighted_sum_of_measured_dimensions():
    out = risk_score(_indicators())
    # 0.35*60 + 0.20*70 + 0.15*30 + 0.15*(100-10) + 0.15*(100-30)
    expected = 21.0 + 14.0 + 4.5 + 13.5 + 10.5
    assert out["score"] == pytest.approx(expected, abs=0.1)
    assert sum(out["weights"].values()) == pytest.approx(1.0)


def test_risk_score_uses_complements_for_inverted_dimensions():
    # 情绪指数越高越不悲观，补数分量必须趋近 0，不能被"指数 100"直接当成
    # "100 分危险"算进去。权威缺口同理：有编辑把关的样本占满时缺口为 0。
    ind = _indicators(**{
        "dimensions": [
            {"key": "negative_share", "value": 0.0},
            {"key": "attention_burst", "value": 0.0},
            {"key": "low_credibility_share", "value": 0.0},
            {"key": "authority_share", "value": 100.0},
            {"key": "sentiment_index", "value": 100.0},
        ],
        "sample": {"total": 50, "known_days": 7, "tier1": 30, "tier2": 20,
                   "tier4": 0, "undated": 0},
    })
    out = risk_score(ind)
    assert out["components"]["authority_gap"] == 0.0
    assert out["components"]["sentiment_pessimism"] == 0.0
    assert out["score"] == 0.0


def test_risk_score_authority_gap_counts_only_ungated_sources():
    # 缺口 = T3 + T4 占比。T1/T2 都有编辑审核，能当事实层；转载和自媒体不能。
    ind = _indicators(**{
        "dimensions": [{"key": "negative_share", "value": 0.0}],
        "sample": {"total": 100, "known_days": 7, "tier1": 10, "tier2": 20,
                   "tier4": 10, "undated": 0},
    })
    out = risk_score(ind)
    # 100 - 10 - 20 = 70 条无把关
    assert out["components"]["authority_gap"] == 70.0


def test_risk_score_authority_gap_does_not_saturate_without_wire_coverage():
    # 回归：早先用 1 − 权威占比（T1），企业新闻几乎拿不到通讯社稿，
    # 缺口恒为 100、风险恒判"高"。T1 为 0 但 T2 占四成时缺口应只有六成。
    ind = _indicators(**{
        "dimensions": [{"key": "negative_share", "value": 0.0}],
        "sample": {"total": 100, "known_days": 7, "tier1": 0, "tier2": 40,
                   "tier4": 0, "undated": 0},
    })
    out = risk_score(ind)
    assert out["components"]["authority_gap"] == 60.0


def test_risk_score_missing_dimension_is_zero_not_worst_case():
    # 没测权威占比、也没有样本分层时记 0 而不是 100：否则"没测"会被算成
    # "最坏"，而它只是缺失。
    out = risk_score(_indicators(**{
        "dimensions": [{"key": "negative_share", "value": 50.0}],
        "sample": {"total": 0},
    }))
    assert out["components"]["authority_gap"] == 0.0
    assert out["components"]["sentiment_pessimism"] == 0.0


def test_risk_level_bands():
    assert risk_level(10.0)["level"] == "low"
    assert risk_level(29.9)["level"] == "low"
    assert risk_level(30.0)["level"] == "medium"
    assert risk_level(54.9)["level"] == "medium"
    assert risk_level(55.0)["level"] == "high"
    assert risk_level(74.9)["level"] == "high"
    assert risk_level(75.0)["level"] == "critical"
    assert risk_level(75.0)["label"] == "紧急"


# ── 趋势方向 ──────────────────────────────────────────────────────

def _daily(rows):
    """rows: [(date, volume, sentiment_index)]"""
    return [{"date": d, "volume": v, "sentiment_index": s} for d, v, s in rows]


def test_trend_direction_heating_when_late_volume_dominates():
    days = _daily([("2026-09-15", 10, 40), ("2026-09-16", 10, 40),
                   ("2026-09-17", 30, 40), ("2026-09-18", 40, 40)])
    out = trend_direction({"daily": days})
    assert out["direction"] == "heating"
    # 前半段日均 10 条，后半段日均 35 条
    assert out["volume_ratio"] == pytest.approx(3.5)


def test_trend_direction_cooling_when_volume_collapses():
    days = _daily([("2026-09-15", 40, 40), ("2026-09-16", 30, 40),
                   ("2026-09-17", 10, 40), ("2026-09-18", 10, 40)])
    out = trend_direction({"daily": days})
    assert out["direction"] == "cooling"


def test_trend_direction_flat_when_volume_stable():
    days = _daily([("2026-09-15", 20, 40), ("2026-09-16", 20, 40),
                   ("2026-09-17", 22, 40), ("2026-09-18", 21, 40)])
    out = trend_direction({"daily": days})
    assert out["direction"] == "flat"


def test_trend_direction_reversal_when_sentiment_crosses_neutral():
    # 立场换边优先于声量方向：前后两段情绪指数跨过 50 中性线。
    days = _daily([("2026-09-15", 10, 70), ("2026-09-16", 10, 72),
                   ("2026-09-17", 10, 25), ("2026-09-18", 10, 28)])
    out = trend_direction({"daily": days})
    assert out["direction"] == "reversal_risk"
    assert out["label"] == "反转风险"


def test_trend_direction_reversal_on_large_swing_without_crossing():
    days = _daily([("2026-09-15", 10, 90), ("2026-09-16", 10, 92),
                   ("2026-09-17", 10, 65), ("2026-09-18", 10, 68)])
    out = trend_direction({"daily": days})
    assert out["direction"] == "reversal_risk"


def test_trend_direction_unknown_when_too_few_dated_days():
    days = _daily([("2026-09-15", 10, 40), ("2026-09-16", 10, 40)])
    out = trend_direction({"daily": days})
    assert out["direction"] == "unknown"
    assert out["label"] == "样本不足"
    assert "少于 3 天" in out["basis"]


def test_trend_direction_ignores_unknown_date_bucket():
    days = _daily([("2026-09-15", 10, 40), ("2026-09-16", 10, 40),
                   ("2026-09-17", 10, 40), ("2026-09-18", 10, 40)])
    days.append({"date": "unknown", "volume": 999, "sentiment_index": 5})
    out = trend_direction({"daily": days})
    assert out["direction"] == "flat"


def test_trend_direction_empty_and_none_days():
    assert trend_direction({})["direction"] == "unknown"
    assert trend_direction({"daily": None})["direction"] == "unknown"


# ── 观察窗口 ──────────────────────────────────────────────────────

def test_observation_window_reports_real_span():
    days = _daily([("2026-09-15", 10, 40), ("2026-09-18", 10, 40), ("unknown", 3, None)])
    out = observation_window({"daily": days, "sample": {
        "known_days": 2, "total": 13, "undated": 3, "sources": 4}})
    assert out["from"] == "2026-09-15"
    assert out["to"] == "2026-09-18"
    assert out["days"] == 2
    assert out["samples"] == 13
    assert out["undated"] == 3


def test_observation_window_empty():
    out = observation_window({})
    assert out["from"] is None
    assert out["to"] is None
    assert out["samples"] == 0


# ── 核心证据 ──────────────────────────────────────────────────────

def test_core_evidence_prefers_lower_tier_then_recency():
    items = [
        _news(1, tier=4, day="2026-09-18"),
        _news(2, tier=2, day="2026-09-10"),
        _news(3, tier=1, day="2026-09-15"),
    ]
    picked = core_evidence(items, "negative", limit=3)
    assert [p["source_tier"] for p in picked] == [1, 2, 4]
    assert picked[0]["title"] == "标题 3"


def test_core_evidence_aligns_with_stance():
    items = [
        _news(1, tier=1, day="2026-09-18", label="positive"),
        _news(2, tier=1, day="2026-09-18", label="negative"),
        _news(3, tier=1, day="2026-09-18", label="neutral"),
    ]
    picked = core_evidence(items, "negative", limit=3)
    assert picked[0]["sentiment_label"] == "negative"
    assert picked[-1]["sentiment_label"] == "positive"


def test_core_evidence_skips_untitled_entries():
    items = [{"source": "x"}, _news(1, tier=1, day="2026-09-15")]
    picked = core_evidence(items, "negative", limit=3)
    assert len(picked) == 1
    assert picked[0]["title"] == "标题 1"


def test_core_evidence_shows_the_headline_not_the_tokenized_form():
    # DataCleaner 把 title 切成带空格的词序列喂分词器，original_title 才是
    # 原题。核心依据要拿去向用户求证，不能显示"宁德 时代 市值 蒸发"。
    item = _news(1, tier=1, day="2026-09-15")
    item["original_title"] = '宁德时代市值蒸发近万亿：当车企不再需要"技术代差"'
    picked = core_evidence([item], "negative", limit=3)
    assert picked[0]["title"] == '宁德时代市值蒸发近万亿：当车企不再需要"技术代差"'


def test_core_evidence_falls_back_to_title_when_no_original():
    picked = core_evidence([_news(1, tier=1, day="2026-09-15")], "negative", limit=3)
    assert picked[0]["title"] == "标题 1"


def test_core_evidence_empty_and_limit():
    assert core_evidence([], "negative") == []
    assert len(core_evidence([_news(i) for i in range(10)], "negative", limit=3)) == 3


# ── 待验证项 ──────────────────────────────────────────────────────

def test_watch_items_includes_model_disagreements_and_data_gaps():
    verdict = {"key_disagreements": ["红方认为监管已介入", "蓝方认为影响可控"]}
    out = watch_items(verdict, _indicators())
    assert "红方认为监管已介入" in out
    assert "蓝方认为影响可控" in out
    # tier4=15/50=30% 不触发 >30%；T1+T2=5/50=10% 触发 <20% 的把关缺口。
    # 所以这一轮除两条分歧外，只应再多出把关缺口这一条。
    assert len(out) == 3
    assert any("T1+T2" in i for i in out)


def test_watch_items_flags_low_credibility_majority():
    out = watch_items({}, _indicators(**{"sample": {
        "total": 20, "known_days": 5, "tier1": 0, "tier2": 0, "tier4": 9, "undated": 0}}))
    assert any("低可信来源" in i for i in out)
    assert any("T1+T2" in i for i in out)


def test_watch_items_flags_small_sample():
    out = watch_items({}, _indicators(**{"sample": {
        "total": 6, "known_days": 3, "tier1": 0, "tier4": 0, "undated": 0}}))
    assert any("6 条样本" in i for i in out)


def test_watch_items_dedupes_and_caps():
    verdict = {"key_disagreements": ["同一条", "同一条", "另一条"]}
    out = watch_items(verdict, {"sample": {"total": 0}})
    assert out.count("同一条") == 1
    assert len(out) == 2


def test_watch_items_empty():
    assert watch_items({}, {}) == []


# ── 整卡组装 ──────────────────────────────────────────────────────

def test_build_verdict_card_full_shape():
    news = [_news(i, tier=1, day="2026-09-1%d" % (i % 10)) for i in range(20)]
    card = build_verdict_card(
        keyword="某事件",
        verdict={"stance": "negative", "confidence": 0.8,
                 "summary": "负面声量持续放大", "recommendation": "持续观察"},
        indicators=_indicators(),
        analyzed_news=news,
    )
    assert card["keyword"] == "某事件"
    assert card["stance"] == "negative"
    assert card["headline"] == "负面声量持续放大"
    assert card["risk"]["level"] == "high"
    assert 0 <= card["risk"]["score"] <= 100
    assert card["confidence"] == 0.8
    assert card["low_confidence"] is False
    assert card["window"]["samples"] == 50
    assert len(card["core_evidence"]) == 3
    assert card["recommendation"] == "持续观察"
    assert card["method_note"]


def test_build_verdict_card_downgrades_confidence_on_small_sample():
    # 模型自评 0.9，但样本只有 6 条：卡片必须把置信压到 0.5 并标记，
    # 不能让模型的一句"很确定"盖住样本量不足这个事实。
    news = [_news(i, tier=1, day="2026-09-18") for i in range(6)]
    card = build_verdict_card(
        keyword="k",
        verdict={"stance": "negative", "confidence": 0.9},
        indicators=_indicators(**{"sample": {
            "total": 6, "known_days": 3, "tier1": 0, "tier4": 0, "undated": 0}}),
        analyzed_news=news,
    )
    assert card["low_confidence"] is True
    assert card["confidence"] == 0.5


def test_build_verdict_card_works_without_llm_verdict():
    # 裁判 LLM 不可用时只缺措辞，可测部分必须完整。
    card = build_verdict_card(
        keyword="k", verdict={}, indicators=_indicators(),
        analyzed_news=[_news(1, tier=1, day="2026-09-15")],
    )
    assert card["stance"] == "neutral"
    assert card["headline"] == ""
    assert card["risk"]["level"] == "high"
    assert card["trend"]["direction"] == "unknown"


def test_build_verdict_card_tolerates_empty_inputs():
    card = build_verdict_card(keyword="k", verdict=None, indicators={}, analyzed_news=None)
    assert card["risk"]["score"] == 0.0
    assert card["risk"]["level"] == "low"
    assert card["core_evidence"] == []
    assert card["trend"]["direction"] == "unknown"


def test_build_verdict_card_risk_is_independent_of_model_wording():
    # 同一批指标 + 不同模型措辞 → 风险分与等级必须一致。
    a = build_verdict_card(keyword="k", verdict={"stance": "negative", "summary": "甲"},
                           indicators=_indicators(), analyzed_news=[])
    b = build_verdict_card(keyword="k", verdict={"stance": "positive", "summary": "乙乙乙乙乙乙"},
                           indicators=_indicators(), analyzed_news=[])
    assert a["risk"] == b["risk"]
    assert a["trend"] == b["trend"]


def test_build_verdict_card_with_real_indicators_pipeline():
    # 走一遍真实 compute_indicators，确认两个模块能对接。
    news = [_news(i, tier=1, day="2026-09-1%d" % (i % 10)) for i in range(12)]
    card = build_verdict_card(
        keyword="某事件", verdict={"stance": "negative", "confidence": 0.7},
        indicators=compute_indicators(news), analyzed_news=news)
    assert card["window"]["samples"] == 12
    assert card["risk"]["score"] > 0
    assert card["core_evidence"]
