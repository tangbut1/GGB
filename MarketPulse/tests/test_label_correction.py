"""情绪标签校正的行为约定。

校正改的是"这批里该有多少条算负面"这个分布判断，不是单条文本的实测
分数。把分数一起钳掉会让所有负面条目的情绪分变成同一个值，极化度指标
结构上永远为 0——这里把这两条钉死。
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.agents.sentiment_agent import SentimentAgent  # noqa: E402


def _news(score):
    return {"title": f"t{score}", "sentiment_score": score,
            "sentiment_label": "neutral"}


def _agent():
    # 只借静态方法，不实例化（实例化会去读配置和 Key）。
    return SentimentAgent.__new__(SentimentAgent)


class TestApplyLabelCorrection:
    def setup_method(self):
        self.apply = _agent()._apply_label_correction

    def test_preserves_the_measured_score(self):
        news = [_news(-0.9), _news(-0.4), _news(-0.05), _news(0.3), _news(0.8)]
        self.apply(news, {"negative_count": 2, "positive_count": 1})
        by_score = {round(n["sentiment_score"], 3): n for n in news}
        # 标签按分布重排了，但分数必须还是 SnowNLP 测出来的原值
        assert sorted(by_score) == [-0.9, -0.4, -0.05, 0.3, 0.8]
        assert by_score[-0.9]["sentiment_label"] == "negative"
        assert by_score[-0.4]["sentiment_label"] == "negative"
        assert by_score[0.8]["sentiment_label"] == "positive"
        assert by_score[-0.05]["sentiment_label"] == "neutral"

    def test_keeps_the_original_label_for_audit(self):
        news = [_news(-0.9)]
        news[0]["sentiment_label"] = "neutral"
        self.apply(news, {"negative_count": 1, "positive_count": 0})
        assert news[0]["sentiment_label"] == "negative"
        assert news[0]["sentiment_label_algo"] == "neutral"

    def test_does_not_clobber_an_existing_algo_label(self):
        news = [_news(-0.9)]
        news[0]["sentiment_label_algo"] = "positive"
        self.apply(news, {"negative_count": 1, "positive_count": 0})
        # setdefault：已经记过原标签就不再覆盖，避免二次校正把最初的
        # 算法判断冲掉。
        assert news[0]["sentiment_label_algo"] == "positive"

    def test_polarization_stays_measurable(self):
        # 极性样本占比是核心指标。分数一旦被钳到 ±0.15，|分数| ≥ 0.6 的
        # 样本数恒为 0，这个指标就再也动不了。
        news = [_news(-0.9), _news(-0.85), _news(0.7), _news(0.1), _news(-0.2)]
        self.apply(news, {"negative_count": 3, "positive_count": 1})
        polar = sum(1 for n in news if abs(n["sentiment_score"]) >= 0.6)
        assert polar == 3

    def test_never_labels_one_item_both_negative_and_positive(self):
        news = [_news(-0.9), _news(-0.5), _news(0.2), _news(0.6)]
        # neg + pos > total 的极端输入
        self.apply(news, {"negative_count": 4, "positive_count": 3})
        labels = [n["sentiment_label"] for n in news]
        assert labels.count("negative") + labels.count("positive") <= len(news)
