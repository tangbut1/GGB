"""舆情多维指标。

只用一条"情绪指数"评价一次舆情是站不住的：同一个均值既可能来自
"少量极端负面 + 大量中立"，也可能来自"温和的全面偏负"，两者的风险
含义完全不同。所以这里从同一批已打分的样本里算出若干**互相独立**的
维度，每个维度都给出归一化值（0-100，便于横向比较）和原始值（可复现）。

原则：所有数值都由实测样本算出，没有任何占位、插值或行业基准。
样本不足时对应的维度会带 ``sufficient: False``，界面必须说明口径，
不能画成一个看着像有数据的图。
"""

from __future__ import annotations

import math
from typing import Any, Dict, List

# 情绪打分的两极阈值。SnowNLP 对中文财经文本系统性低报负面，绝对分数
# 只用于内部分层，不作为"负面占比"的依据——那个用标签。
_POLAR_THRESHOLD = 0.6
# 声量归一化的参考上限：1000 条记满分。取对数，避免几百条和几千条
# 在图上看起来一样。
_VOLUME_REF = 1000


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if isinstance(value, bool):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _day_of(item: Dict[str, Any]) -> str:
    """取发布日期（YYYY-MM-DD）。取不到就归到 'unknown'，不猜。"""
    raw = str(item.get("publish_time") or "").strip()
    if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
        return raw[:10]
    return "unknown"


def _normalize(value: float, low: float, high: float) -> float:
    """线性映射到 0-100 并裁剪。"""
    if high <= low:
        return 0.0
    return round(max(0.0, min(1.0, (value - low) / (high - low))) * 100, 1)


def _concentration(counts: Dict[str, int]) -> float:
    """信源集中度的反面：1 - HHI（赫芬达尔指数）。

    不用归一化香农熵：熵按 log(来源数) 归一，来源只有两三个时分母很小，
    9:1 这种近乎单一站点的分布仍能算出 47 分，读起来像"中等多元"，
    而它显然不构成多方印证。1 - HHI 以"单一来源 = 0"为绝对零点，
    与来源个数无关，更贴合"这是不是同一条消息被反复转载"这个问题。
    """
    total = sum(counts.values())
    if total <= 0:
        return 0.0
    hhi = sum((c / total) ** 2 for c in counts.values())
    return 1.0 - hhi


def daily_series(analyzed_news: list) -> list:
    """按天聚合的真实序列。

    没有发布日期的样本单独归为一组（``date='unknown'``），不丢也不编日期。
    序列按日期排序，unknown 排在最后。
    """
    buckets: Dict[str, Dict[str, Any]] = {}
    for item in analyzed_news:
        if not isinstance(item, dict):
            continue
        day = _day_of(item)
        b = buckets.setdefault(day, {
            "date": day, "volume": 0, "score_sum": 0.0, "scored": 0,
            "negative": 0, "tier1": 0,
        })
        b["volume"] += 1
        score = item.get("sentiment_score")
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            b["score_sum"] += _safe_float(score)
            b["scored"] += 1
        if str(item.get("sentiment_label", "")).lower() == "negative":
            b["negative"] += 1
        if _safe_float(item.get("source_tier"), 4) <= 1:
            b["tier1"] += 1

    out = []
    for day in sorted(buckets, key=lambda d: (d == "unknown", d)):
        b = buckets[day]
        out.append({
            "date": day,
            "volume": b["volume"],
            "sentiment_index": round((b["score_sum"] / b["scored"] + 1) / 2 * 100, 1) if b["scored"] else None,
            "negative_share": round(b["negative"] / b["volume"] * 100, 1),
            "t1_share": round(b["tier1"] / b["volume"] * 100, 1),
        })
    return out


def compute_indicators(analyzed_news: list) -> dict:
    """算出全部维度。返回 ``{"dimensions": [...], "daily": [...], "sample": {...}}``。"""
    items = [n for n in (analyzed_news or []) if isinstance(n, dict)]
    total = len(items)
    if total == 0:
        return {"dimensions": [], "daily": [], "sample": {"total": 0}}

    scored = [n for n in items
              if isinstance(n.get("sentiment_score"), (int, float))
              and not isinstance(n.get("sentiment_score"), bool)]
    scores = [_safe_float(n.get("sentiment_score")) for n in scored]

    negative = sum(1 for n in items if str(n.get("sentiment_label", "")).lower() == "negative")
    positive = sum(1 for n in items if str(n.get("sentiment_label", "")).lower() == "positive")
    neutral = total - negative - positive

    tiers = [int(_safe_float(n.get("source_tier"), 4)) for n in items]
    tier1 = sum(1 for t in tiers if t <= 1)
    tier2 = sum(1 for t in tiers if t == 2)
    tier4 = sum(1 for t in tiers if t >= 4)

    sources: Dict[str, int] = {}
    for n in items:
        key = str(n.get("source_domain") or n.get("source") or "").strip() or "unknown"
        sources[key] = sources.get(key, 0) + 1

    mean_score = sum(scores) / len(scores) if scores else 0.0
    variance = sum((s - mean_score) ** 2 for s in scores) / len(scores) if scores else 0.0
    polar = sum(1 for s in scores if abs(s) >= _POLAR_THRESHOLD)

    # 一条都没打分时情绪指数必须是 None 而不是 50：0 分映射后正好落在
    # "完全中性"上，那等于把"没有数据"显示成"数据说中性"。
    sentiment_index = _normalize(mean_score, -1, 1) if scores else None

    series = daily_series(items)
    known_days = [d for d in series if d["date"] != "unknown"]
    undated = next((d["volume"] for d in series if d["date"] == "unknown"), 0)
    peak_day = max(series, key=lambda d: d["volume"]) if series else None
    mean_vol = sum(d["volume"] for d in known_days) / len(known_days) if known_days else 0.0
    burst_ratio = (peak_day["volume"] / mean_vol) if (peak_day and mean_vol > 0) else 0.0
    burst_display = (
        f"{peak_day['date']} · {peak_day['volume']} 条 = 日均的 {round(burst_ratio, 2)} 倍"
        if peak_day and peak_day["date"] != "unknown"
        else "无有效日期，无法判断"
    )

    dims = [
        {
            "key": "sentiment_index",
            "label": "情绪指数",
            "value": sentiment_index,
            "raw": round(mean_score, 3) if scores else None,
            "display": (f"{round(mean_score, 3):+.3f}" if scores else "无打分样本"),
            "hint": "全部样本情绪分的均值，映射到 0-100。50 为中性，越低越负面。",
            "basis": f"{len(scored)}/{total} 条样本的 sentiment_score 均值",
            "sufficient": len(scored) >= 5,
        },
        {
            "key": "negative_share",
            "label": "负面占比",
            "value": round(negative / total * 100, 1),
            "raw": round(negative / total * 100, 1),
            "display": f"{negative}/{total}（{round(negative / total * 100, 1)}%）",
            "hint": "负面样本的绝对占比。和情绪指数分开看：均值尚可但负面占比高，"
                    "说明少数极端个案在拉低整体。",
            "basis": "sentiment_label == negative 的条数 / 总条数",
            "sufficient": total >= 5,
        },
        {
            "key": "polarization",
            "label": "情绪极化",
            "value": round(polar / len(scores) * 100, 1) if scores else None,
            "raw": polar if scores else None,
            "display": (
                f"{polar} 条（{round(polar / len(scores) * 100, 1)}%）" if scores else "无打分样本"
            ),
            "hint": f"情绪分绝对值 ≥ {_POLAR_THRESHOLD} 的样本占比。越高说明立场越两极，"
                    "温和共识少——这种舆情转向也快。",
            "basis": f"|sentiment_score| ≥ {_POLAR_THRESHOLD} 的条数 / 已打分条数",
            "sufficient": len(scores) >= 5,
        },
        {
            "key": "volume",
            "label": "声量强度",
            "value": _normalize(math.log10(1 + total), 0, math.log10(1 + _VOLUME_REF)),
            "raw": total,
            "display": f"{total} 条",
            "hint": f"采集到的样本总量，按 log10 归一（{_VOLUME_REF} 条记 100）。"
                    "声量本身不带立场，但决定了下面每个比例的统计意义。",
            "basis": f"样本总数（对数归一，参考上限 {_VOLUME_REF}）",
            "sufficient": total >= 10,
        },
        {
            "key": "source_diversity",
            "label": "信源多样性",
            "value": round(_concentration(sources) * 100, 1),
            "raw": len(sources),
            "display": f"{len(sources)} 个来源",
            "hint": "1 - 赫芬达尔指数（HHI），100 表示均匀分散在各来源，0 表示全部来自单一站点——"
                    "后者只是同一条消息被反复转载，不能当作多方印证。",
            "basis": "按 source_domain 统计的 1 - Σ(占比²)",
            "sufficient": total >= 10,
        },
        {
            "key": "authority_share",
            "label": "权威信源占比",
            "value": round(tier1 / total * 100, 1),
            "raw": tier1,
            "display": f"{tier1}/{total}（{round(tier1 / total * 100, 1)}%）",
            "hint": "T1 权威通讯社/央媒/监管机构占比。这一项决定了情绪分布有多少"
                    "能当事实读——T4 自媒体只作情绪信号。",
            "basis": "source_tier ≤ 1 的条数 / 总条数",
            "sufficient": total >= 5,
        },
        {
            "key": "low_credibility_share",
            "label": "低可信占比",
            "value": round(tier4 / total * 100, 1),
            "raw": tier4,
            "display": f"{tier4}/{total}（{round(tier4 / total * 100, 1)}%）",
            "hint": "T4 自媒体/论坛占比。偏高时整体情绪会被放大，结论要相应打折。",
            "basis": "source_tier ≥ 4 的条数 / 总条数",
            "sufficient": total >= 5,
        },
        {
            "key": "attention_burst",
            "label": "关注度峰值",
            "value": _normalize(burst_ratio, 1, 5),
            "raw": round(burst_ratio, 2),
            "display": burst_display,
            "hint": "单日最高声量相对日均的倍数（1-5 倍映射到 0-100）。"
                    "尖峰通常对应事件爆发点，也是舆情最可能继续升温的位置。",
            "basis": "单日最大条数 / 已知日期的日均条数",
            "sufficient": len(known_days) >= 2,
        },
        {
            "key": "date_coverage",
            "label": "日期覆盖",
            "value": _normalize(len(known_days), 1, 30),
            "raw": len(known_days),
            "display": f"{len(known_days)} 天" + (f"（{undated} 条无日期）" if undated else ""),
            "hint": "样本覆盖的自然日天数。少于 3 天时任何时序预测都没有意义，"
                    "此时只应读横截面指标。",
            "basis": "publish_time 可解析出的不同日期数",
            "sufficient": len(known_days) >= 2,
        },
    ]

    return {
        "dimensions": dims,
        "daily": series,
        "sample": {
            "total": total,
            "scored": len(scored),
            "positive": positive,
            "neutral": max(neutral, 0),
            "negative": negative,
            "sources": len(sources),
            "tier1": tier1,
            "tier2": tier2,
            "tier4": tier4,
            "known_days": len(known_days),
            "undated": undated,
            "score_std": round(math.sqrt(variance), 3),
        },
    }
