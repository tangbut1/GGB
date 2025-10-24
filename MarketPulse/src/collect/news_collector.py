import os
import json
import hashlib
import feedparser
import requests
import time
from datetime import datetime
from pathlib import Path
from loguru import logger


class NewsCollector:
    """多源财经新闻采集器 - 支持多个RSS源，自动去重和容错"""

    def __init__(self):
        self.data_dir = Path(__file__).resolve().parents[2] / "data"
        self.data_dir.mkdir(exist_ok=True)
        
        # 多源RSS配置（自动fallback）
        self.rss_feeds = [
            "https://rss.sina.com.cn/finance/china/focus15.xml",   # 新浪财经焦点
            "https://rss.sina.com.cn/finance/global/index.xml",   # 新浪国际财经
            "https://rss.sina.com.cn/finance/china/stock20.xml",  # 新浪股票
            "https://finance.eastmoney.com/rss/stock.xml",        # 东方财富
            "https://finance.yahoo.com/news/rssindex",             # 雅虎财经
            "https://feeds.finance.yahoo.com/rss/2.0/headline",    # 雅虎财经头条
        ]

    def fetch_latest(self):
        """从多个RSS源抓取新闻"""
        all_news = []
        successful_sources = 0
        
        for url in self.rss_feeds:
            logger.info(f"Fetching news from {url} ...")
            try:
                # 使用feedparser抓取RSS
                feed = feedparser.parse(url)
                
                if not feed.entries:
                    logger.warning(f"No entries found in {url}")
                    continue
                
                source_news = []
                for entry in feed.entries:
                    # 标准化数据结构
                    item = {
                        "title": entry.get("title", "").strip(),
                        "link": entry.get("link", "").strip(),
                        "published": entry.get("published", ""),
                        "summary": entry.get("summary", "").strip(),
                        "source": url  # 添加来源标识
                    }
                    
                    # 过滤空标题
                    if item["title"]:
                        source_news.append(item)
                
                all_news.extend(source_news)
                successful_sources += 1
                logger.success(f"✅ 成功从 {url} 获取 {len(source_news)} 条新闻")
                
            except Exception as e:
                logger.error(f"❌ 从 {url} 抓取失败: {e}")
                continue
        
        logger.info(f"📊 总计从 {successful_sources}/{len(self.rss_feeds)} 个源获取 {len(all_news)} 条新闻")
        return all_news

    def clean_and_deduplicate(self, news_list):
        """清洗与去重新闻"""
        if not news_list:
            logger.warning("No news to clean.")
            return []
        
        # 使用MD5哈希去重
        unique_news = {}
        duplicates_removed = 0
        
        for news in news_list:
            title = news.get("title", "").strip()
            if not title:
                continue
                
            # 生成唯一标识符
            content_hash = hashlib.md5(title.encode("utf-8")).hexdigest()
            
            if content_hash not in unique_news:
                unique_news[content_hash] = news
            else:
                duplicates_removed += 1
        
        cleaned_news = list(unique_news.values())
        logger.info(f"🧹 去重完成: 原始 {len(news_list)} 条 -> 去重后 {len(cleaned_news)} 条 (移除 {duplicates_removed} 条重复)")
        return cleaned_news

    def save_news(self, news_list):
        """保存新闻到文件"""
        if not news_list:
            logger.warning("No news to save.")
            return
        
        # 保存原始数据
        raw_file_path = self.data_dir / "raw" / "raw_news.json"
        raw_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(raw_file_path, "w", encoding="utf-8") as f:
            json.dump(news_list, f, ensure_ascii=False, indent=2)
        
        logger.success(f"✅ 已保存 {len(news_list)} 条新闻到 {raw_file_path}")

    def safe_request(self, url, retries=3, delay=2):
        """安全的HTTP请求，带重试机制"""
        for attempt in range(retries):
            try:
                response = requests.get(url, timeout=10, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                })
                if response.status_code == 200:
                    return response.text
            except requests.RequestException as e:
                logger.warning(f"Attempt {attempt+1} failed for {url}: {e}")
                if attempt < retries - 1:
                    time.sleep(delay)
        
        logger.error(f"All attempts failed for {url}")
        return None

    def run_full_pipeline(self):
        """运行完整的新闻采集流程"""
        logger.info("🚀 开始多源新闻采集...")
        
        # 1. 抓取新闻
        raw_news = self.fetch_latest()
        
        if not raw_news:
            logger.error("❌ 未能获取任何新闻，请检查网络连接或RSS源")
            return []
        
        # 2. 清洗去重
        cleaned_news = self.clean_and_deduplicate(raw_news)
        
        # 3. 保存数据
        self.save_news(cleaned_news)
        
        logger.success(f"🎉 新闻采集完成！共获取 {len(cleaned_news)} 条有效新闻")
        return cleaned_news

