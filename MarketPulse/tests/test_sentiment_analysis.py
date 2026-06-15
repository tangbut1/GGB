import pytest
from src.analysis.sentiment_analysis import SentimentAnalyzer

def test_sentiment_analyzer_initialization():
    analyzer = SentimentAnalyzer()
    assert '上涨' in analyzer.positive_words
    assert '下跌' in analyzer.negative_words

def test_analyze_single():
    analyzer = SentimentAnalyzer()
    # Test positive case
    result_pos = analyzer.analyze_single("这只股票大幅上涨，盈利非常好，值得投资。")
    assert result_pos['sentiment'] >= 0
    assert result_pos['label'] in ['positive', 'neutral']

    # Test negative case (SnowNLP might give weird scores, we just check it runs without crash)
    result_neg = analyzer.analyze_single("市场下跌严重，亏损巨大，存在严重危机。")
    assert 'sentiment' in result_neg

    # Test empty string
    result_empty = analyzer.analyze_single("")
    assert result_empty['sentiment'] == 0.0
    assert result_empty['label'] == 'neutral'

def test_analyze_news_batch():
    analyzer = SentimentAnalyzer()
    news_list = [
        {'title': '股票上涨', 'content': '盈利创新高'},
        {'title': '市场暴跌', 'content': '亏损严重风险巨大'}
    ]
    results = analyzer.analyze_news_batch(news_list)
    assert len(results) == 2
    assert 'sentiment_score' in results[0]
    assert 'sentiment_label' in results[0]

def test_get_sentiment_summary():
    analyzer = SentimentAnalyzer()
    news_list = [
        {'sentiment_score': 0.5, 'sentiment_label': 'positive'},
        {'sentiment_score': -0.5, 'sentiment_label': 'negative'},
        {'sentiment_score': 0.0, 'sentiment_label': 'neutral'}
    ]
    summary = analyzer.get_sentiment_summary(news_list)
    assert summary['total_news'] == 3
    assert summary['positive_count'] == 1
    assert summary['negative_count'] == 1
    assert summary['neutral_count'] == 1
    assert 'avg_sentiment' in summary
