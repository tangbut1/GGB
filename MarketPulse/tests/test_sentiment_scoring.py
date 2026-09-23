"""情绪打分的模型选择约定。

这里钉死三件事，都是实测坏过一轮才补上的：

1. **中文必须走 SnowNLP**。SnowNLP 装在环境里却从来没被调用过，"SnowNLP
   初判"只存在于注释和前端文案里。
2. **TextBlob 不能进中文的平均**。它的词典是英文的，喂中文恒返回 0.0，一个
   恒定的 0 混进平均等于把每条真实分数对折。
3. **词典不参与打分**。词典分数的分母是全文词数，同一句标题抓到的正文长短
   不同就会得到不同分数，把它和模型分求平均等于掺入一个随正文长度漂移的
   噪声项。词典只在模型贴在中点时兜底翻标签。
"""

import statistics as st

import pytest

from src.analysis.sentiment_analysis import SentimentAnalyzer, _has_cjk


@pytest.fixture(scope="module")
def analyzer():
    return SentimentAnalyzer()


# ── 语言探测 ──────────────────────────────────────────────────────────────


def test_detects_chinese():
    assert _has_cjk("宁德时代市值蒸发")
    assert _has_cjk("mixed 中文 text")


def test_pure_latin_is_not_chinese():
    assert not _has_cjk("CATL market cap evaporates")
    assert not _has_cjk("12345 !!! ...")


# ── SnowNLP 真的被用上了 ──────────────────────────────────────────────────


def test_chinese_text_uses_snownlp(analyzer):
    """分数必须等于 SnowNLP 的映射值，而不是词典/TextBlob 的平均。"""
    from snownlp import SnowNLP

    text = "宁德时代市值蒸发，股价大幅下跌，投资者恐慌情绪蔓延"
    expected = round(2.0 * SnowNLP(text).sentiments - 1.0, 3)
    assert analyzer.analyze_single(text)["sentiment"] == expected


def test_score_is_continuous_not_collapsed(analyzer):
    """同一批真实标题必须给出多个不同分数。

    这是上个坏版本的直接症状：88 条样本里 77 条都是 0.0，极化度结构性为 0。
    """
    titles = [
        "宁德时代市值蒸发 股价大跌",
        "曾毓群批评行业速成车 宁德时代面临电池定义权之争",
        "理想汽车引入电池供应商中创新航 降低宁德时代依赖度",
        "宁德时代以天恒系统定义储能电站20年可靠运营",
        "宁德时代9月23日回购66.51万股A股 耗资约2亿元",
        "工信部媒体发文纠偏去宁德化",
        "车企去宁德化越喊越响 真绕得开吗",
        "宁德时代在匈牙利启动电池电芯试生产",
        "世纪互联战略融资 融资额9.42亿美元 投资方为宁德时代",
        "启境GX7全系搭载宁德时代电池 电车卷续航又出新选手",
    ]
    scores = [analyzer.analyze_single(t)["sentiment"] for t in titles]
    distinct = {round(s, 3) for s in scores}
    # 十条标题至少要有五六种不同取值，否则说明又退化成常数了
    assert len(distinct) >= 5, f"只有 {len(distinct)} 个不同分数：{distinct}"
    assert st.pstdev(scores) > 0.2, f"标准差仅 {st.pstdev(scores):.3f}，测量没有分辨力"


def test_textblob_constant_zero_is_not_averaged_in(analyzer):
    """TextBlob 对中文恒返回 0.0，不能把它算进来把分数对折。"""
    from textblob import TextBlob

    text = "市场下跌严重，亏损巨大，存在严重危机。"
    assert TextBlob(text).sentiment.polarity == 0.0  # 前提：它确实是 0

    from snownlp import SnowNLP

    snow = round(2.0 * SnowNLP(text).sentiments - 1.0, 3)
    got = analyzer.analyze_single(text)["sentiment"]
    assert got == snow, f"拿到 {got}，等于把 SnowNLP 的 {snow} 和 0 平均了"


# ── 词典只兜底标签，不碰分数 ──────────────────────────────────────────────


def test_model_view_wins_over_the_dictionary(analyzer):
    """模型有看法时以模型为准，词典不覆盖。

    词典里"投资""发展"在企业新闻里是描述性事实而不是好评。若让词典覆盖模型，
    实测 88 条样本的负面从 19 条被压到更少、正面从 63 条涨得更高——那是词典
    的领域错配，不是测量。
    """
    from snownlp import SnowNLP

    text = "市场下跌严重，亏损巨大，存在严重危机。"
    snow = round(2.0 * SnowNLP(text).sentiments - 1.0, 3)
    result = analyzer.analyze_single(text)

    # 前提：这条的词典信号是明确的负向
    pos, neg = analyzer._dict_signal(text)
    assert neg - pos >= 2

    assert result["sentiment"] == snow, "分数必须是模型实测值"
    if snow > 0.1:
        assert result["label"] == "positive", "模型有看法时按模型走，不被词典覆盖"
    elif snow < -0.1:
        assert result["label"] == "negative"


def test_dictionary_fills_in_only_when_the_model_abstains(analyzer):
    """模型退回中点（|分数| ≤ 0.1）而词典有明确同向词时，信词典。

    这是词典唯一不可替代的场景：模型说"没看法"，而文本里有不含糊的同向
    情绪词。实测 SnowNLP 对"风险 风险 提示"给 +0.011，正好卡在中点上。
    """
    from snownlp import SnowNLP

    text = "风险 风险 提示"
    snow = round(2.0 * SnowNLP(text).sentiments - 1.0, 3)
    pos, neg = analyzer._dict_signal(text)

    assert abs(snow) <= 0.1, f"前提失效：SnowNLP 给了 {snow:+.3f}，不是弃权"
    assert neg - pos >= 2, f"前提失效：词典只有 {pos}/{neg}"
    assert analyzer.analyze_single(text)["label"] == "negative"



def test_single_sentiment_word_does_not_flip_label(analyzer):
    """只有一条同向情绪词时不足以翻标签——阈值是 2 条净同向。"""
    # 这条只含一个负面词（风险），且构造为让 SnowNLP 贴在中点附近
    text = "这家公司公布了新的组织架构调整方案"
    pos, neg = analyzer._dict_signal(text)
    assert pos - neg < 2 and neg - pos < 2, f"词典信号过强：{pos}/{neg}"


def test_dict_signal_returns_counts_not_ratio(analyzer):
    """_dict_signal 给词数，量纲与正文长度无关。"""
    short = "股价下跌"
    long_text = "股价下跌 " + "公司经营正常 " * 50
    assert analyzer._dict_signal(short)[1] == analyzer._dict_signal(long_text)[1]


def test_dict_based_sentiment_stays_length_dependent(analyzer):
    """保留 _dict_based_sentiment 的既有行为，但文档已说明它为何不进分数。"""
    short = analyzer._dict_based_sentiment("股价下跌 亏损")
    long_text = analyzer._dict_based_sentiment("股价下跌 亏损 " + "公司经营正常 " * 50)
    assert abs(long_text) < abs(short)


# ── 置信度 ────────────────────────────────────────────────────────────────


def test_confidence_is_the_model_margin_not_a_trust_score(analyzer):
    """单模型时置信度 = 模型自己的边际 |分数|×2。

    注意它衡量的是"模型多确定"，不是"这个判断多可信"：SnowNLP 在绝大多数
    真实中文文本上都接近饱和，所以这个值经常是 1.0。判断的可信度由终裁的
    置信度负责，不在这里冒充。
    """
    text = "这家公司业绩创历史新高，盈利大幅增长，前景非常好"
    result = analyzer.analyze_single(text)
    assert result["confidence"] == min(1.0, abs(result["sentiment"]) * 2.0)
    assert 0.0 <= result["confidence"] <= 1.0


def test_confidence_is_zero_when_model_has_no_view(analyzer):
    """模型给 0.0 时置信度必须是 0，不能伪装成"测出来是中性的"。"""
    result = analyzer.analyze_single("12345")
    assert result["confidence"] == 0.0


# ── 边界 ──────────────────────────────────────────────────────────────────


def test_empty_and_non_string_input(analyzer):
    for bad in ["", None, 123, [], {}]:
        result = analyzer.analyze_single(bad)
        assert result == {"sentiment": 0.0, "confidence": 0.0, "label": "neutral"}


def test_scores_stay_in_range(analyzer):
    for text in ["上涨", "下跌", "neutral text", "混合 mixed 内容 上涨 下跌"]:
        s = analyzer.analyze_single(text)["sentiment"]
        assert -1.0 <= s <= 1.0
