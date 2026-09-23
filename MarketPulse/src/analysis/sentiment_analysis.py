import json
import numpy as np
from typing import List, Dict, Any, Tuple
from pathlib import Path
from transformers import pipeline
from textblob import TextBlob
import jieba
from collections import Counter

from ..net_safety import safe_write_path


def _torch_available() -> bool:
    """ transformers 的 pipeline 需要 torch/tf/flax 之一，缺一个都跑不起来。

    只做 import 探测，不下载任何东西。requirements.txt 里没有 torch，
    所以正常情况下这里返回 False，FinBERT 一路直接跳过。
    """
    try:
        import torch  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


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
        
        # 初始化 FinBERT 模型。
        # FinBERT 是这一路的加分项而不是必需项：没装 torch 时整条流水线
        # 靠「财经词典 + SnowNLP」照样能跑。这里先探一次 torch，装不上
        # 就连模型都不去下载——否则每次 new SentimentAnalyzer() 都会先试着
        # 拉一个几百 MB 的模型再失败，既慢又在日志里刷一句吓人的报错。
        self.finbert_pipeline = None
        if _torch_available():
            try:
                self.finbert_pipeline = pipeline("sentiment-analysis", model="yiyanghkust/finbert-tone-chinese")
            except Exception as e:
                print(f"FinBERT 模型加载失败，本次运行改用词典 + SnowNLP：{e}")
        else:
            print("未检测到 PyTorch，FinBERT 不可用；本次运行使用财经词典 + SnowNLP。")
    
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
        
        # 2. FinBERT情绪分析
        finbert_score = self._finbert_sentiment(text)
        
        # 3. TextBlob情绪分析（英文）
        textblob_score = self._textblob_sentiment(text)
        
        # 4. 融合多个模型的结果
        scores = [dict_score, finbert_score, textblob_score]
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
    
    def _finbert_sentiment(self, text: str) -> float:
        """FinBERT情绪分析"""
        if not self.finbert_pipeline:
            return None
        try:
            # BERT limits sequence length to 512 tokens.
            # We slice the string loosely to prevent crash.
            result = self.finbert_pipeline(text[:500])[0]
            label = result['label']
            score = result['score']
            
            if label == 'Positive':
                return float(score)
            elif label == 'Negative':
                return -float(score)
            else:
                return 0.0
        except Exception:
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

            news_with_sentiment = news.copy()

            # 已经打过分就直接复用。追问轮会把首轮的 analyzed_news 再送进来，
            # SnowNLP 是确定性的（同样输入同样输出），重算一遍只会白烧 CPU：
            # 300 条语料要跑好几秒，用户点一次追问就卡一次。
            if isinstance(news.get('sentiment_score'), (int, float)):
                analyzed_news.append(news_with_sentiment)
                continue

            # 合并标题和内容进行分析
            text = f"{news.get('title', '')} {news.get('content', '')} {news.get('summary', '')}"

            sentiment_result = self.analyze_single(text)

            # 添加情绪分析结果到新闻数据
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
        # file_path 只往 safe_write_path 里流：先校验再派生目录，避免
        # "上游传什么就用什么"拼出一条没把过关的路径。
        target = safe_write_path(file_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        results = {
            'summary': summary,
            'detailed_results': analyzed_news
        }

        target.write_text(
            json.dumps(results, ensure_ascii=False, indent=2),
            encoding='utf-8')

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
