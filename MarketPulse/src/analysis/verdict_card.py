"""研判卡：把实测指标压成一张能直接做决策的结论卡。

产品要给的结论是"当前态势是什么、我该关注什么"，不是"几个 Agent 说了
什么"。这张卡就是那个结论。它分两部分，界限必须划清楚：

- **可测的**（风险分、趋势方向、观察窗口、核心证据）由本批样本算出，
  完全确定性、可复现。LLM 不可用的时候这些照样成立。
- **要解释的**（一句话结论、待验证项）来自裁判 LLM，是对实测结果的解读。

把两类混在一起会让"模型说了算"悄悄替换掉"数据说了算"——所以风险分和
趋势方向一律不交给模型，模型的 headline 只做措辞，不改判级。

原则与 sentiment_indicators 一致：所有数值来自实测，没有占位、插值或
行业基准；样本不足时明确说不足，不画一个看着像有数据的图。
"""

from __future__ import annotations

from typing import Any, Dict, List

# 风险分的权重。写在这里而不是藏在代码里，是因为卡上要把它原样展示给
# 用户——一个说不清怎么来的"高风险"和编出来的没有区别。
_RISK_WEIGHTS = {
    "negative_share": 0.35,       # 负面占比：态势本身有多坏
    "attention_burst": 0.20,      # 关注度峰值：是否在扩散
    "low_credibility_share": 0.15,  # 低可信占比：信号有多噪
    "authority_gap": 0.15,        # 无编辑把关的样本占比：有多少不能当事实读
    "sentiment_pessimism": 0.15,  # 情绪指数的悲观端
}

# 风险分档。阈值是约定的，不是拟合出来的——所以卡上要连权重一起展示，
# 让读者能自己复算，而不是只看到一个等级词。
_RISK_BANDS = [(30, "low", "低"), (55, "medium", "中"), (75, "high", "高")]
_RISK_TOP = ("critical", "紧急")

# 样本量门槛。低于这个数时比例没有统计意义，卡上必须降置信并说明，
# 不能拿 6 条样本算出的"负面占比 50%"去支撑一个高风险判断。
_MIN_SAMPLES_FOR_RATIOS = 10
_MIN_DAYS_FOR_TREND = 3


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if isinstance(value, bool):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _dim(indicators: Dict[str, Any], key: str) -> Dict[str, Any]:
    for d in (indicators or {}).get("dimensions", []) or []:
        if isinstance(d, dict) and d.get("key") == key:
            return d
    return {}


def _known_days(indicators: Dict[str, Any]) -> List[Dict[str, Any]]:
    """只取有真实日期的按天序列，unknown 排在最后的那条不算。"""
    return [d for d in (indicators or {}).get("daily", []) or []
            if isinstance(d, dict) and d.get("date") not in (None, "", "unknown")]


def _authority_gap(indicators: Dict[str, Any],
                   authority: Dict[str, Any]) -> float:
    """没有编辑把关的样本占比，0-100。

    早先用 100 - 权威占比（T1）当缺口，结果任何不含通讯社/央媒的话题
    （绝大多数企业新闻、地方事件都是）缺口直接顶到 100，风险分系统性
    偏高，"高"变成默认档、不再有分辨力。

    真正该问的是"这批样本里有多少条没有事实核查流程"：T1 和 T2 都有
    编辑审核，T3 以转载为主、T4 是自媒体，两者都无法当事实依据。所以
    缺口按 T3 + T4 的占比算。两者都取不到时退化成 100 - 权威占比，
    并明确这是退化口径。
    """
    sample = (indicators or {}).get("sample") or {}
    total = _f(sample.get("total"))
    if total > 0:
        gated = _f(sample.get("tier1")) + _f(sample.get("tier2"))
        return max(0.0, min(100.0, (total - gated) / total * 100.0))
    if authority:
        return 100.0 - _f(authority.get("value"))
    return 0.0


def risk_score(indicators: Dict[str, Any]) -> Dict[str, Any]:
    """加权风险分 0-100，附每个分量的贡献值。"""
    neg = _dim(indicators, "negative_share")
    burst = _dim(indicators, "attention_burst")
    low_cred = _dim(indicators, "low_credibility_share")
    authority = _dim(indicators, "authority_share")
    sentiment = _dim(indicators, "sentiment_index")

    components = {
        "negative_share": _f(neg.get("value")),
        "attention_burst": _f(burst.get("value")),
        "low_credibility_share": _f(low_cred.get("value")),
        # 没有编辑把关的样本越多，情绪分布越不能当事实读。
        "authority_gap": _authority_gap(indicators, authority),
        # 情绪指数 50 为中性，越接近 0 越悲观，同样取补数。
        "sentiment_pessimism": (100.0 - _f(sentiment.get("value"))) if sentiment else 0.0,
    }

    score = sum(_RISK_WEIGHTS[k] * v for k, v in components.items())
    return {
        "score": round(max(0.0, min(100.0, score)), 1),
        "components": {k: round(v, 1) for k, v in components.items()},
        "weights": dict(_RISK_WEIGHTS),
    }


def risk_level(score: float) -> Dict[str, Any]:
    for ceiling, level, label in _RISK_BANDS:
        if score < ceiling:
            return {"level": level, "label": label}
    level, label = _RISK_TOP
    return {"level": level, "label": label}


def trend_direction(indicators: Dict[str, Any]) -> Dict[str, Any]:
    """升温 / 降温 / 横盘 / 反转风险。

    反转风险和前三者是不同性质的问题：升温降温说的是"声量还在不在涨"，
    反转说的是"立场本身在换边"。所以先判立场翻转，再判声量方向。
    """
    days = _known_days(indicators)
    if len(days) < _MIN_DAYS_FOR_TREND:
        return {
            "direction": "unknown",
            "label": "样本不足",
            "basis": f"仅有 {len(days)} 个有日期的自然日，少于 {_MIN_DAYS_FOR_TREND} 天，"
                     "时序方向没有统计意义",
            "volume_ratio": None,
            "sentiment_shift": None,
        }

    half = len(days) // 2
    early, late = days[:half], days[half:]

    def _mean(rows, key):
        vals = [_f(r.get(key)) for r in rows if r.get(key) is not None]
        return sum(vals) / len(vals) if vals else None

    early_s, late_s = _mean(early, "sentiment_index"), _mean(late, "sentiment_index")
    early_v, late_v = _mean(early, "volume"), _mean(late, "volume")

    volume_ratio = (late_v / early_v) if (early_v and late_v is not None) else None
    sentiment_shift = (late_s - early_s) if (early_s is not None and late_s is not None) else None

    # 立场换边：前后两段情绪指数跨过中性线（50），或摆幅超过 20 分。
    crossed = (early_s is not None and late_s is not None
               and (early_s - 50) * (late_s - 50) < 0)
    swung = sentiment_shift is not None and abs(sentiment_shift) > 20

    if crossed or swung:
        direction, label = "reversal_risk", "反转风险"
        basis = (f"情绪指数从前半段 {early_s:.1f} 变为后半段 {late_s:.1f}"
                 if sentiment_shift is not None else "情绪指数发生跨段变化")
    elif volume_ratio is not None and volume_ratio > 1.3:
        direction, label = "heating", "升温"
        basis = f"后半段日均声量是前半段的 {volume_ratio:.2f} 倍"
    elif volume_ratio is not None and volume_ratio < 0.7:
        direction, label = "cooling", "降温"
        basis = f"后半段日均声量是前半段的 {volume_ratio:.2f} 倍"
    else:
        direction, label = "flat", "横盘"
        basis = (f"后半段日均声量是前半段的 {volume_ratio:.2f} 倍"
                 if volume_ratio is not None else "声量无显著变化")

    return {
        "direction": direction,
        "label": label,
        "basis": basis,
        "volume_ratio": round(volume_ratio, 2) if volume_ratio is not None else None,
        "sentiment_shift": round(sentiment_shift, 1) if sentiment_shift is not None else None,
    }


def observation_window(indicators: Dict[str, Any]) -> Dict[str, Any]:
    sample = (indicators or {}).get("sample", {}) or {}
    days = _known_days(indicators)
    return {
        "days": sample.get("known_days", len(days)),
        "samples": sample.get("total", 0),
        "from": days[0]["date"] if days else None,
        "to": days[-1]["date"] if days else None,
        "undated": sample.get("undated", 0),
        "sources": sample.get("sources", 0),
    }


def core_evidence(analyzed_news: List[Dict[str, Any]], stance: str,
                  limit: int = 3) -> List[Dict[str, Any]]:
    """挑出最支撑结论的几条证据。

    排序口径写死在函数里而不是交给模型：先看信源层级（T1 一手采编优先
    于 T4 转载），再看时间（新的优先），最后按与终裁立场的一致性微调。
    这样"核心依据"是可复现的选取，不是模型挑顺眼的。
    """
    usable = [n for n in (analyzed_news or [])
              if isinstance(n, dict) and (n.get("title") or n.get("original_title"))]

    def display_title(item):
        # title 经过 DataCleaner 的 jieba 切分，词与词之间带空格
        # （"宁德 时代 市值 蒸发"），那是喂给分词器的形态，不是给人看的。
        # original_title 是搜索引擎给的原题，核心依据要拿去向用户求证，
        # 标题必须是原题。
        return str(item.get("original_title") or item.get("title") or "").strip()[:120]

    def sort_key(item):
        tier = int(_f(item.get("source_tier"), 4))
        label = str(item.get("sentiment_label", "")).lower()
        # 立场一致的点往前排；中性的排在一致与相反之间。
        if stance == "negative":
            align = {"negative": 0, "neutral": 1, "positive": 2}.get(label, 1)
        elif stance == "positive":
            align = {"positive": 0, "neutral": 1, "negative": 2}.get(label, 1)
        else:
            align = 0
        date = str(item.get("publish_time") or "")
        return (tier, align, [-ord(c) for c in date])

    picked = sorted(usable, key=sort_key)[:limit]
    return [{
        "title": display_title(n),
        "source": str(n.get("source") or n.get("source_domain") or "未知来源"),
        "source_domain": str(n.get("source_domain") or ""),
        "source_tier": int(_f(n.get("source_tier"), 4)),
        "publish_time": str(n.get("publish_time") or "")[:10],
        "sentiment_label": str(n.get("sentiment_label", "")),
        "url": str(n.get("url") or n.get("link") or ""),
    } for n in picked]


def watch_items(verdict: Dict[str, Any], indicators: Dict[str, Any]) -> List[str]:
    """待验证项：把模型指出的分歧和样本自身的短板合起来。

    分歧来自裁判（它看见了双方论点），短板来自实测（低可信占比高、权威
    占比低这类"这批数据本身不能证明什么"）。后者模型看不见全貌，必须
    由数据侧补。
    """
    items: List[str] = []
    for d in (verdict or {}).get("key_disagreements", []) or []:
        text = str(d).strip()
        if text:
            items.append(text[:120])

    sample = (indicators or {}).get("sample", {}) or {}
    total = int(_f(sample.get("total")))
    if total and total < _MIN_SAMPLES_FOR_RATIOS:
        items.append(f"本次仅采集到 {total} 条样本，比例类指标波动大，结论需更多样本复核")
    if total:
        tier4 = _f(sample.get("tier4"))
        if tier4 / total > 0.3:
            items.append(
                f"低可信来源（T4）占 {round(tier4 / total * 100, 1)}%，"
                "高传播内容可能缺少一手证据，建议核对原始通报"
            )
        tier1 = _f(sample.get("tier1"))
        tier2 = _f(sample.get("tier2"))
        gated = tier1 + tier2
        if total and gated / total < 0.2:
            items.append(
                f"有一线采编或编辑审核的信源（T1+T2）仅占 "
                f"{round(gated / total * 100, 1)}%，事实层主要靠转载拼合，"
                "关键数字建议回溯原始出处"
            )
    undated = int(_f(sample.get("undated")))
    if undated:
        items.append(f"有 {undated} 条样本无法解析发布日期，未参与时序判断")

    # 去重但保序，避免模型重复输出同一条时分占两行
    seen, out = set(), []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out[:5]


def build_verdict_card(*, keyword: str, verdict: Dict[str, Any],
                       indicators: Dict[str, Any],
                       analyzed_news: List[Dict[str, Any]]) -> Dict[str, Any]:
    """组装研判卡。任何一部分数据缺失都不抛异常，缺就说缺。"""
    verdict = verdict or {}
    indicators = indicators or {}

    sample = indicators.get("sample", {}) or {}
    total = int(_f(sample.get("total")))
    rscore = risk_score(indicators)
    level = risk_level(rscore["score"])
    direction = trend_direction(indicators)
    window = observation_window(indicators)

    # 样本不足时风险等级必须降级说明：否则 6 条样本也能给出"高风险"，
    # 而那个分数没有任何统计意义。
    low_confidence = total < _MIN_SAMPLES_FOR_RATIOS or window["days"] < _MIN_DAYS_FOR_TREND
    confidence = _f(verdict.get("confidence"), 0.0)
    if low_confidence:
        confidence = min(confidence, 0.5)

    return {
        "keyword": keyword,
        "headline": str(verdict.get("summary") or "")[:200],
        "stance": str(verdict.get("stance", "neutral")),
        "risk": {
            **level,
            "score": rscore["score"],
            "components": rscore["components"],
            "weights": rscore["weights"],
        },
        "trend": direction,
        "confidence": round(confidence, 2),
        "low_confidence": low_confidence,
        "window": window,
        "core_evidence": core_evidence(analyzed_news, str(verdict.get("stance", "neutral"))),
        "watch_items": watch_items(verdict, indicators),
        "recommendation": str(verdict.get("recommendation") or "")[:120],
        # 口径说明。卡上每个数字都要能回答"怎么算的"，否则用户无法复核。
        "method_note": (
            f"风险分由 {len(_RISK_WEIGHTS)} 个实测维度加权得出（权重见下）；"
            f"其中「权威缺口」= 无编辑把关的样本（T3 转载 + T4 自媒体）占比，"
            "不是 1 − 权威占比，否则不含通讯社的话题会被系统性判高。"
            f"趋势方向由 {window['days']} 个有日期的自然日的前后半段对比得出，"
            "核心证据按信源层级与发布时间排序选取。以上均为确定性计算，不随模型变化。"
        ),
    }
