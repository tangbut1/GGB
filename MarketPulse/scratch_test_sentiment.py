import json
from src.analysis.sentiment_analysis import SentimentAnalyzer

with open("data/raw/custom_search_特斯拉_1780216266.json", "r", encoding="utf-8") as f:
    news_data = json.load(f)

print(f"Loaded {len(news_data)} news articles.")
analyzer = SentimentAnalyzer()
try:
    analyzed = analyzer.analyze_news_batch(news_data)
    print("Success. Analyzed", len(analyzed))
except Exception as e:
    import traceback
    traceback.print_exc()
