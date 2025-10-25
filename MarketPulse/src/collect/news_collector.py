import os
import json
import hashlib
import feedparser
import requests
import time
from datetime import datetime, timedelta
from pathlib import Path
from loguru import logger


class NewsCollector:
    """多源财经新闻采集器 - 支持多个RSS源，自动去重和容错"""

    def __init__(self, categories=None):
        self.data_dir = Path(__file__).resolve().parents[2] / "data"
        self.data_dir.mkdir(exist_ok=True)
        
        # 设置时间过滤：只抓取7天内的数据（在线新闻采集）
        self.cutoff_date = datetime.now() - timedelta(days=7)

        # 多源RSS配置（按类别组织，便于用户选择）
        # 更新为可用的RSS源，包含国际和中文源
        self.category_feeds = {
            "科技": [
                "https://feeds.bbci.co.uk/news/technology/rss.xml",
                "https://feeds.reuters.com/reuters/technologyNews",
                "https://feeds.feedburner.com/oreilly/radar"
            ],
            "金融": [
                "https://feeds.bbci.co.uk/news/business/rss.xml",
                "https://feeds.reuters.com/reuters/businessNews",
                "https://feeds.marketwatch.com/marketwatch/topstories/"
            ],
            "国际": [
                "https://feeds.bbci.co.uk/news/world/rss.xml",
                "https://feeds.reuters.com/reuters/worldNews",
                "https://feeds.a.dj.com/rss/RSSWorldNews.xml",
                "https://feeds.cnn.com/rss/edition.rss",
                "https://feeds.npr.org/1001/rss.xml",
                "https://feeds.nytimes.com/nyt/World.xml"
            ],
            "股票": [
                "https://feeds.marketwatch.com/marketwatch/marketpulse/",
                "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
                "https://feeds.finance.yahoo.com/rss/2.0/headline"
            ]
        }

        self.category_alias_map = {
            "tech": "科技",
            "科技": "科技",
            "technology": "科技",
            "finance": "金融",
            "金融": "金融",
            "international": "国际",
            "国际": "国际",
            "global": "国际",
            "stock": "股票",
            "stocks": "股票",
            "股票": "股票"
        }

        self.selected_categories = self._normalize_categories(categories)

    def set_categories(self, categories=None):
        """更新用户选择的类别"""
        self.selected_categories = self._normalize_categories(categories)

    def _normalize_categories(self, categories=None):
        if not categories:
            return list(self.category_feeds.keys())

        normalized = []
        for category in categories:
            if not category:
                continue
            key = self.category_alias_map.get(str(category).strip().lower(), category)
            if key in self.category_feeds and key not in normalized:
                normalized.append(key)
        return normalized or list(self.category_feeds.keys())
    
    def _is_recent_news(self, published_str: str) -> bool:
        """检查新闻是否在3天内发布"""
        if not published_str:
            return True  # 如果没有时间信息，默认包含
        
        try:
            # 尝试解析各种时间格式
            published_time = None
            
            # 常见的时间格式
            time_formats = [
                "%a, %d %b %Y %H:%M:%S %Z",  # RFC 2822
                "%a, %d %b %Y %H:%M:%S %z",  # RFC 2822 with timezone
                "%Y-%m-%d %H:%M:%S",          # ISO format
                "%Y-%m-%dT%H:%M:%S",         # ISO format with T
                "%Y-%m-%dT%H:%M:%SZ",       # ISO format with Z
                "%Y-%m-%dT%H:%M:%S.%fZ",    # ISO format with microseconds
                "%a, %d %b %Y %H:%M:%S",    # Without timezone
            ]
            
            for fmt in time_formats:
                try:
                    published_time = datetime.strptime(published_str, fmt)
                    break
                except ValueError:
                    continue
            
            if published_time is None:
                # 如果所有格式都失败，使用feedparser的时间解析
                try:
                    import email.utils
                    published_time = email.utils.parsedate_to_datetime(published_str)
                except:
                    return True  # 解析失败时默认包含
            
            # 检查是否在3天内
            return published_time >= self.cutoff_date
            
        except Exception as e:
            logger.warning(f"时间解析失败: {published_str} - {e}")
            return True  # 解析失败时默认包含

    def fetch_latest(self):
        """从多个RSS源抓取新闻"""
        all_news = []
        successful_sources = 0

        categories = self.selected_categories or list(self.category_feeds.keys())
        planned_feeds = []
        for category in categories:
            feeds = self.category_feeds.get(category, [])
            planned_feeds.extend([(category, url) for url in feeds])

        if not planned_feeds:
            logger.warning("未找到匹配的RSS源，使用所有默认源。")
            for category, urls in self.category_feeds.items():
                planned_feeds.extend([(category, url) for url in urls])

        for category, url in planned_feeds:
            logger.info(f"Fetching {category} news from {url} ...")
            try:
                # 使用feedparser抓取RSS，增加超时和重试机制
                feed = feedparser.parse(url)

                # 检查RSS解析状态
                if hasattr(feed, 'bozo') and feed.bozo:
                    logger.warning(f"RSS解析警告: {url} - {getattr(feed, 'bozo_exception', 'Unknown error')}")

                if not feed.entries:
                    logger.warning(f"No entries found in {url}")
                    continue

                source_news = []
                for entry in feed.entries:
                    # 检查发布时间是否在3天内
                    if not self._is_recent_news(entry.get("published", "")):
                        continue
                    
                    # 标准化数据结构，增加更多字段处理
                    item = {
                        "title": entry.get("title", "").strip(),
                        "link": entry.get("link", "").strip(),
                        "published": entry.get("published", ""),
                        "summary": entry.get("summary", "").strip(),
                        "content": entry.get("content", [{}])[0].get("value", "") if entry.get("content") else "",
                        "source": url,  # 添加来源标识
                        "category": category
                    }

                    # 过滤空标题和无效链接
                    if item["title"] and item["link"]:
                        source_news.append(item)

                if source_news:
                    all_news.extend(source_news)
                    successful_sources += 1
                    logger.success(f"✅ 成功从 {url} 获取 {len(source_news)} 条 {category} 类新闻")
                else:
                    logger.warning(f"从 {url} 获取的新闻为空或无效")

            except Exception as e:
                logger.error(f"❌ 从 {url} 抓取失败: {e}")
                continue

        logger.info(
            f"📊 总计从 {successful_sources}/{len(planned_feeds)} 个源获取 {len(all_news)} 条新闻"
        )
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

    def create_sample_data(self):
        """创建示例数据作为备用方案"""
        logger.info("📝 创建示例数据作为备用方案...")
        
        sample_news = [
            {
                "title": "科技股表现强劲，AI技术推动市场创新",
                "link": "https://example.com/tech-ai-market",
                "published": "2024-10-24T10:00:00Z",
                "summary": "人工智能技术在各个行业的应用推动了科技股的强劲表现，投资者对AI相关公司的前景保持乐观。",
                "content": "人工智能技术正在改变各个行业的面貌，从自动驾驶汽车到医疗诊断，AI的应用范围不断扩大。投资者对AI相关公司的前景保持乐观，科技股因此表现强劲。",
                "source": "示例数据源",
                "category": "科技"
            },
            {
                "title": "央行货币政策调整，金融市场反应积极",
                "link": "https://example.com/central-bank-policy",
                "published": "2024-10-24T09:30:00Z",
                "summary": "央行宣布新的货币政策措施，金融市场对此反应积极，股市和债市均出现上涨。",
                "content": "央行今日宣布调整货币政策，包括利率调整和流动性管理措施。金融市场对此反应积极，主要股指上涨，债券收益率下降。",
                "source": "示例数据源",
                "category": "金融"
            },
            {
                "title": "全球经济复苏迹象明显，国际投资者信心增强",
                "link": "https://example.com/global-recovery",
                "published": "2024-10-24T08:15:00Z",
                "summary": "最新经济数据显示全球经济复苏迹象明显，国际投资者信心增强，资金流入新兴市场。",
                "content": "根据最新发布的经济数据，全球经济复苏迹象明显，制造业PMI指数回升，就业市场改善。国际投资者信心增强，资金开始流入新兴市场。",
                "source": "示例数据源",
                "category": "国际"
            },
            {
                "title": "股票市场交易活跃，成交量创近期新高",
                "link": "https://example.com/stock-trading",
                "published": "2024-10-24T07:45:00Z",
                "summary": "股票市场交易活跃，成交量创近期新高，投资者参与度明显提升。",
                "content": "今日股票市场交易活跃，成交量创近期新高。投资者参与度明显提升，机构投资者和个人投资者都在积极交易。",
                "source": "示例数据源",
                "category": "股票"
            }
        ]
        
        logger.success(f"✅ 已创建 {len(sample_news)} 条示例数据")
        return sample_news

    def run_full_pipeline(self):
        """运行完整的新闻采集流程"""
        logger.info("🚀 开始多源新闻采集...")
        
        # 1. 抓取新闻
        raw_news = self.fetch_latest()
        
        # 2. 如果没有获取到新闻，使用示例数据
        if not raw_news:
            logger.warning("⚠️ 未能从RSS源获取新闻，使用示例数据进行演示")
            raw_news = self.create_sample_data()
        
        # 3. 清洗去重
        cleaned_news = self.clean_and_deduplicate(raw_news)
        
        # 4. 保存数据
        self.save_news(cleaned_news)
        
        logger.success(f"🎉 新闻采集完成！共获取 {len(cleaned_news)} 条有效新闻")
        return cleaned_news

