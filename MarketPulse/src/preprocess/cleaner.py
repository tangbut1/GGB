import re
import jieba
from typing import List, Dict, Any
import json


class DataCleaner:
    """数据清洗器 - 处理新闻文本数据"""
    
    def __init__(self):
        # 初始化jieba分词
        jieba.initialize()
        
        # 财经相关停用词
        self.stop_words = {
            '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这',
            '公司', '企业', '市场', '经济', '投资', '股票', '基金', '银行', '金融', '证券', '交易', '价格', '上涨', '下跌', '涨幅', '跌幅'
        }
    
    def clean_text(self, text: str) -> str:
        """
        清洗单个文本
        
        Args:
            text: 原始文本
            
        Returns:
            清洗后的文本
        """
        if not text or not isinstance(text, str):
            return ""
        
        # 1. 去除HTML标签
        text = re.sub(r'<[^>]+>', '', text)
        
        # 2. 去除特殊字符和多余空格
        text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        
        # 3. 去除数字和英文单词（保留中文）
        text = re.sub(r'[a-zA-Z0-9]+', '', text)
        
        # 4. 去除停用词
        words = jieba.lcut(text)
        cleaned_words = [word for word in words if word not in self.stop_words and len(word) > 1]
        
        return ' '.join(cleaned_words).strip()
    
    def clean_news_batch(self, news_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        批量清洗新闻数据
        
        Args:
            news_list: 新闻列表
            
        Returns:
            清洗后的新闻列表
        """
        cleaned_news = []
        
        for news in news_list:
            if not isinstance(news, dict):
                continue
                
            cleaned_item = {
                'title': self.clean_text(news.get('title', '')),
                'content': self.clean_text(news.get('content', '')),
                'summary': self.clean_text(news.get('summary', '')),
                'url': news.get('url') or news.get('link', ''),
                'publish_time': news.get('publish_time', news.get('published', '')),
                'source': news.get('source', ''),
                'category': news.get('category', ''),
                'original_title': news.get('title', ''),
                'original_summary': news.get('summary', ''),
                'original_content': news.get('content', '')
            }
            
            # 只保留有内容的新闻
            if cleaned_item['title'] or cleaned_item['content']:
                cleaned_news.append(cleaned_item)
        
        return cleaned_news
    
    def extract_keywords(self, text: str, top_k: int = 10) -> List[str]:
        """
        提取关键词
        
        Args:
            text: 文本
            top_k: 返回前k个关键词
            
        Returns:
            关键词列表
        """
        if not text:
            return []
        
        words = jieba.lcut(text)
        word_freq = {}
        
        for word in words:
            if len(word) > 1 and word not in self.stop_words:
                word_freq[word] = word_freq.get(word, 0) + 1
        
        # 按频率排序
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        return [word for word, freq in sorted_words[:top_k]]
    
    def save_cleaned_data(self, cleaned_news: List[Dict[str, Any]], file_path: str = "data/processed/cleaned_news.json"):
        """
        保存清洗后的数据
        
        Args:
            cleaned_news: 清洗后的新闻数据
            file_path: 保存路径
        """
        import os
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(cleaned_news, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 已保存 {len(cleaned_news)} 条清洗后的新闻到 {file_path}")


def clean_text(text: str) -> str:
    """
    便捷函数：清洗单个文本
    
    Args:
        text: 原始文本
        
    Returns:
        清洗后的文本
    """
    cleaner = DataCleaner()
    return cleaner.clean_text(text)
