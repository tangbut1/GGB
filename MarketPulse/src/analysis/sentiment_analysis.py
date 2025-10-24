import json
import numpy as np
from typing import List, Dict, Any, Tuple
from pathlib import Path
import snownlp
from textblob import TextBlob
import jieba
from collections import Counter


class SentimentAnalyzer:
    """情绪分析器 - 多模型融合分析"""
    
    def __init__(self):
        # 财经情绪词典
        self.positive_words = {
            '上涨', '增长', '盈利', '利好', '突破', '创新高', '涨幅', '收益', '投资', '发展',
            '增长', '上涨', '利好', '突破', '创新', '收益', '盈利', '发展', '投资', '涨幅',
            '积极', '乐观', '看好', '推荐', '买入', '持有', '上涨', '增长', '盈利', '利好'
        }
        
        self.negative_words = {
            '下跌', '亏损', '利空', '跌破', '创新低', '跌幅', '损失', '风险', '危机', '衰退',
            '下跌', '亏损', '利空', '跌破', '创新低', '跌幅', '损失', '风险', '危机', '衰退',
            '消极', '悲观', '看空', '卖出', '减持', '下跌', '亏损', '利空', '跌破', '创新低'
        }
    
    def analyze_single(self, text: str) -> Dict[str, float]:
        """
        分析单个文本的情绪
        
        Args:
            text: 文本内容
            
        Returns:
            情绪分析结果字典
        """
        if not text or not isinstance(text, str):
            return {'sentiment': 0.0, 'confidence': 0.0, 'label': 'neutral'}
        
        # 1. 基于词典的情绪分析
        dict_score = self._dict_based_sentiment(text)
        
        # 2. SnowNLP情绪分析
        snownlp_score = self._snownlp_sentiment(text)
        
        # 3. TextBlob情绪分析（英文）
        textblob_score = self._textblob_sentiment(text)
        
        # 4. 融合多个模型的结果
        scores = [dict_score, snownlp_score, textblob_score]
        valid_scores = [s for s in scores if s is not None]
        
        if not valid_scores:
            return {'sentiment': 0.0, 'confidence': 0.0, 'label': 'neutral'}
        
        # 计算加权平均
        final_score = np.mean(valid_scores)
        confidence = 1.0 - np.std(valid_scores) if len(valid_scores) > 1 else 0.8
        
        # 确定情绪标签
        if final_score > 0.1:
            label = 'positive'
        elif final_score < -0.1:
            label = 'negative'
        else:
            label = 'neutral'
        
        return {
            'sentiment': round(final_score, 3),
            'confidence': round(confidence, 3),
            'label': label
        }
    
    def _dict_based_sentiment(self, text: str) -> float:
        """基于词典的情绪分析"""
        words = jieba.lcut(text)
        positive_count = sum(1 for word in words if word in self.positive_words)
        negative_count = sum(1 for word in words if word in self.negative_words)
        
        total_words = len(words)
        if total_words == 0:
            return 0.0
        
        score = (positive_count - negative_count) / total_words
        return max(-1.0, min(1.0, score))
    
    def _snownlp_sentiment(self, text: str) -> float:
        """SnowNLP情绪分析"""
        try:
            return snownlp.SnowNLP(text).sentiments
        except:
            return None
    
    def _textblob_sentiment(self, text: str) -> float:
        """TextBlob情绪分析"""
        try:
            blob = TextBlob(text)
            return blob.sentiment.polarity
        except:
            return None
    
    def analyze_batch(self, texts: List[str]) -> List[Dict[str, float]]:
        """
        批量分析文本情绪
        
        Args:
            texts: 文本列表
            
        Returns:
            情绪分析结果列表
        """
        results = []
        for text in texts:
            result = self.analyze_single(text)
            results.append(result)
        return results
    
    def analyze_news_batch(self, news_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        批量分析新闻情绪
        
        Args:
            news_list: 新闻列表
            
        Returns:
            包含情绪分析的新闻列表
        """
        analyzed_news = []
        
        for news in news_list:
            if not isinstance(news, dict):
                continue
            
            # 合并标题和内容进行分析
            text = f"{news.get('title', '')} {news.get('content', '')} {news.get('summary', '')}"
            
            sentiment_result = self.analyze_single(text)
            
            # 添加情绪分析结果到新闻数据
            news_with_sentiment = news.copy()
            news_with_sentiment.update({
                'sentiment_score': sentiment_result['sentiment'],
                'sentiment_confidence': sentiment_result['confidence'],
                'sentiment_label': sentiment_result['label']
            })
            
            analyzed_news.append(news_with_sentiment)
        
        return analyzed_news
    
    def get_sentiment_summary(self, analyzed_news: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        获取情绪分析摘要
        
        Args:
            analyzed_news: 已分析的新闻列表
            
        Returns:
            情绪分析摘要
        """
        if not analyzed_news:
            return {
                'total_news': 0,
                'positive_count': 0,
                'negative_count': 0,
                'neutral_count': 0,
                'avg_sentiment': 0.0,
                'sentiment_distribution': {}
            }
        
        scores = [news.get('sentiment_score', 0) for news in analyzed_news]
        labels = [news.get('sentiment_label', 'neutral') for news in analyzed_news]
        
        positive_count = labels.count('positive')
        negative_count = labels.count('negative')
        neutral_count = labels.count('neutral')
        
        avg_sentiment = np.mean(scores) if scores else 0.0
        
        sentiment_distribution = {
            'positive': positive_count,
            'negative': negative_count,
            'neutral': neutral_count
        }
        
        return {
            'total_news': len(analyzed_news),
            'positive_count': positive_count,
            'negative_count': negative_count,
            'neutral_count': neutral_count,
            'avg_sentiment': round(avg_sentiment, 3),
            'sentiment_distribution': sentiment_distribution
        }
    
    def save_analysis_results(self, analyzed_news: List[Dict[str, Any]], 
                            summary: Dict[str, Any], 
                            file_path: str = "results/logs/sentiment_analysis.json"):
        """
        保存情绪分析结果
        
        Args:
            analyzed_news: 已分析的新闻列表
            summary: 情绪分析摘要
            file_path: 保存路径
        """
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        
        results = {
            'summary': summary,
            'detailed_results': analyzed_news
        }
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 情绪分析结果已保存到 {file_path}")


def analyze_sentiment(text: str) -> Dict[str, float]:
    """
    便捷函数：分析单个文本情绪
    
    Args:
        text: 文本内容
        
    Returns:
        情绪分析结果
    """
    analyzer = SentimentAnalyzer()
    return analyzer.analyze_single(text)
