import json
import re
import numpy as np
from typing import List, Dict, Any, Tuple
from pathlib import Path
from transformers import pipeline
from textblob import TextBlob
import jieba
from collections import Counter
from snownlp import SnowNLP

from ..net_safety import safe_write_path

# 有没有中文。决定该用哪个主测量模型：SnowNLP 只对中文训练过，TextBlob
# 的词典是英文的。
_CJK_RE = re.compile(r'[\u4e00-\u9fff]')

# 词典里同向情绪词要达到几条，才允许在模型贴在中点时翻转标签。用词数而
# 不是词频比例：比例的分母是全文词数，同一句标题抓到的正文长短不同就会
# 得到不同的"比例"，不可比。
_DICT_TIEBREAK_MIN = 2


def _has_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text))


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

        主测量模型按语言选：有中文用 SnowNLP，纯外文用 TextBlob。词典不参与
        打分，只在模型退回中点时补标签——原因见 ``_dict_based_sentiment``。

        曾经的写法是把「词典 + TextBlob」求平均当中文分数，两个都坏：

        - SnowNLP 明明装在环境里却从头到尾没被调用过，所谓"SnowNLP 初判"
          在代码里不存在；
        - TextBlob 的词典是英文的，喂中文恒返回 0.0。一个恒定的 0 混进平均，
          等于把每条真实分数对折。

        两条叠起来的后果是实测 88 条样本里 77 条拿到同一个 0.0：证据卡上每条
        "情绪分"都一样，看起来就是坏数据；极化度（|分数| ≥ 0.6 的占比）结构上
        永远为 0，一个核心指标再也动不了；情绪指数退化成标签占比的线性函数，
        不再是连续测量。

        Args:
            text: 文本内容
            
        Returns:
            情绪分析结果字典
        """
        if not text or not isinstance(text, str):
            return {'sentiment': 0.0, 'confidence': 0.0, 'label': 'neutral'}

        chinese = _has_cjk(text)
        finbert_score = self._finbert_sentiment(text)
        primary = self._snownlp_sentiment(text) if chinese else self._textblob_sentiment(text)

        model_scores = [s for s in (finbert_score, primary) if s is not None]
        if not model_scores:
            # 一个模型都没跑起来时只能说"不知道"。拿词典的微弱信号填一个连续
            # 分数，等于把"没测"伪装成"测出来接近中性"。
            return {'sentiment': 0.0, 'confidence': 0.0, 'label': 'neutral'}

        final_score = float(np.mean(model_scores))
        if len(model_scores) > 1:
            # 两个模型时的分歧度就是不确定性的直接度量
            confidence = 1.0 - float(np.std(model_scores))
        else:
            # 单模型时只能报模型自己的边际。注意 SnowNLP 在绝大多数真实文本上
            # 都接近饱和，所以这个值经常是 1.0——它衡量的是"模型多确定"，
            # 不是"这个判断多可信"。后者由终裁的置信度负责，见 verdict_card。
            confidence = min(1.0, abs(final_score) * 2.0)

        # 词典只在模型明确弃权时补标签。模型有看法时以模型为准——它的偏差
        # （把中文财经负面读成正面）是已知的，由下游 LLM 校正接管，不该在
        # 这里用一个为股评准备的词典去覆盖它：实测那样做会把 88 条里的负面
        # 从 19 条压到、正面从 63 条涨到，因为"投资""发展"这类词在企业新闻
        # 里是描述性事实而不是好评。词典唯一不可替代的场景是模型退回中点、
        # 而文本里有不含糊的同向情绪词。
        pos, neg = self._dict_signal(text)
        if final_score > 0.1:
            label = 'positive'
        elif final_score < -0.1:
            label = 'negative'
        elif pos - neg >= _DICT_TIEBREAK_MIN:
            label = 'positive'
        elif neg - pos >= _DICT_TIEBREAK_MIN:
            label = 'negative'
        else:
            label = 'neutral'

        return {
            'sentiment': round(final_score, 3),
            'confidence': round(max(0.0, confidence), 3),
            'label': label
        }

    def _snownlp_sentiment(self, text: str) -> float:
        """SnowNLP 情绪概率，映射到 [-1, 1]。

        SnowNLP 的 ``sentiments`` 是"这条偏正面"的概率，0.5 是中点。直接减
        0.5 会把可用区间砍掉一半，所以按 ``2p - 1`` 线性映射。

        它是在电商评论上训练的，对中文财经/政治文本**系统性把负面读成正面**。
        这个偏差是已知且被下游接管的：``SentimentAgent`` 会把分布交给 LLM
        校正，前端"情感"Tab 也写明了算法结果只作初判。这里不做二次"纠偏"——
        纠偏曲线是自己造的，无法复现，也比偏差本身更难向用户解释。
        """
        try:
            return round(2.0 * float(SnowNLP(text).sentiments) - 1.0, 3)
        except Exception:  # noqa: BLE001
            return None

    def _dict_based_sentiment(self, text: str) -> float:
        """基于词典的情绪分析。

        注意分母是**全文词数**，所以这个值的量级取决于抓到多少正文，而不取决于
        情绪有多强：同一句标题，一条抓到 800 字正文、一条只抓到标题，哪怕情绪
        词完全一样，算出来的分数也差一个量级。把它和 SnowNLP 求平均等于往连续
        测量里掺入一个随正文长度漂移的噪声项，所以它不再进 ``analyze_single``
        的分数，只用于 :meth:`_dict_signal` 的词数判断。
        """
        words = jieba.lcut(text)
        positive_count = sum(1 for word in words if word in self.positive_words)
        negative_count = sum(1 for word in words if word in self.negative_words)
        
        total_words = len(words)
        if total_words == 0:
            return 0.0
        
        score = (positive_count - negative_count) / total_words
        return max(-1.0, min(1.0, score))

    def _dict_signal(self, text: str) -> Tuple[int, int]:
        """词典命中数：``(正面词数, 负面词数)``。

        用词数而不是比例，才能跨文本比较——见 ``_dict_based_sentiment`` 的说明。
        """
        words = jieba.lcut(text)
        positive_count = sum(1 for word in words if word in self.positive_words)
        negative_count = sum(1 for word in words if word in self.negative_words)
        return positive_count, negative_count
    
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
