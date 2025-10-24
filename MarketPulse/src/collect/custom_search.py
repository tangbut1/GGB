#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import time
import json
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime, timedelta
from loguru import logger
from bs4 import BeautifulSoup
import re


class CustomSearchCollector:
    """自定义搜索新闻采集器 - 根据用户输入的关键词搜索相关新闻"""
    
    def __init__(self):
        self.data_dir = Path(__file__).resolve().parents[2] / "data"
        self.data_dir.mkdir(exist_ok=True)
        
        # 设置时间过滤：只抓取3天内的数据（自定义搜索）
        self.cutoff_date = datetime.now() - timedelta(days=3)
        
        # 搜索源配置
        self.search_sources = {
            "google": {
                "base_url": "https://www.google.com/search",
                "params": {
                    "q": "",  # 搜索关键词
                    "tbm": "nws",  # 新闻搜索
                    "num": "20",   # 结果数量
                    "hl": "zh-CN", # 中文
                    "gl": "CN"     # 中国
                },
                "headers": {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
            },
            "bing": {
                "base_url": "https://www.bing.com/news/search",
                "params": {
                    "q": "",  # 搜索关键词
                    "count": "20",
                    "mkt": "zh-CN"
                },
                "headers": {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            }
        }
    
    def search_news(self, keyword: str, max_results: int = 80) -> List[Dict[str, Any]]:
        """
        根据关键词搜索新闻
        
        Args:
            keyword: 搜索关键词
            max_results: 最大结果数量
            
        Returns:
            新闻列表
        """
        logger.info(f"🔍 开始搜索关键词: {keyword}")
        
        all_news = []
        
        # 从多个源搜索，增加每个源的搜索数量
        per_source_results = max_results // len(self.search_sources)
        for source_name, config in self.search_sources.items():
            try:
                logger.info(f"正在从 {source_name} 搜索...")
                news = self._search_from_source(keyword, source_name, config, per_source_results)
                all_news.extend(news)
                logger.success(f"✅ 从 {source_name} 获取 {len(news)} 条新闻")
            except Exception as e:
                logger.error(f"❌ 从 {source_name} 搜索失败: {e}")
                continue
        
        # 去重
        unique_news = self._deduplicate_news(all_news)
        
        logger.success(f"🎉 搜索完成！共获取 {len(unique_news)} 条相关新闻")
        return unique_news
    
    def _search_from_source(self, keyword: str, source_name: str, config: Dict[str, Any], max_results: int) -> List[Dict[str, Any]]:
        """从指定源搜索新闻"""
        if source_name == "google":
            return self._search_google(keyword, config, max_results)
        elif source_name == "bing":
            return self._search_bing(keyword, config, max_results)
        else:
            return []
    
    def _search_google(self, keyword: str, config: Dict[str, Any], max_results: int) -> List[Dict[str, Any]]:
        """从Google搜索新闻"""
        try:
            # 使用更真实的搜索参数
            params = {
                "q": f"{keyword} news",
                "tbm": "nws",  # 新闻搜索
                "num": str(max_results),
                "hl": "zh-CN",
                "gl": "CN",
                "tbs": "qdr:d"  # 最近一天
            }
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            
            response = requests.get(
                "https://www.google.com/search", 
                params=params, 
                headers=headers,
                timeout=15
            )
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            news_items = []
            
            # 解析Google新闻结果 - 使用更通用的选择器
            news_elements = soup.find_all('div', class_='g') or soup.find_all('div', class_='WlydOe')
            
            for element in news_elements[:max_results]:
                try:
                    # 提取标题 - 尝试多种选择器
                    title_elem = (element.find('h3') or 
                                element.find('div', class_='n0jPhd') or
                                element.find('a', class_='WlydOe'))
                    if not title_elem:
                        continue
                    title = title_elem.get_text().strip()
                    
                    # 提取链接
                    link_elem = element.find('a')
                    if not link_elem:
                        continue
                    link = link_elem.get('href', '')
                    if link.startswith('/url?q='):
                        link = link.split('/url?q=')[1].split('&')[0]
                    
                    # 提取摘要
                    summary_elem = (element.find('div', class_='VwiC3b') or
                                  element.find('div', class_='GI74Re') or
                                  element.find('span', class_='st'))
                    summary = summary_elem.get_text().strip() if summary_elem else ""
                    
                    # 提取来源和时间
                    source_elem = (element.find('span', class_='CEMjEf') or
                                 element.find('span', class_='WF4CUc'))
                    source = source_elem.get_text().strip() if source_elem else "Google搜索"
                    
                    time_elem = (element.find('span', class_='LEwnzc') or
                               element.find('span', class_='f'))
                    publish_time = time_elem.get_text().strip() if time_elem else ""
                    
                    if title and link and len(title) > 5:  # 确保标题有意义
                        # 检查时间是否在3天内
                        if self._is_recent_news(publish_time):
                            news_items.append({
                                "title": title,
                                "link": link,
                                "summary": summary,
                                "source": source,
                                "publish_time": publish_time,
                                "category": "自定义搜索",
                                "search_keyword": keyword
                            })
                except Exception as e:
                    logger.warning(f"解析Google新闻项失败: {e}")
                    continue
            
            return news_items
            
        except Exception as e:
            logger.error(f"Google搜索失败: {e}")
            return []
    
    def _search_bing(self, keyword: str, config: Dict[str, Any], max_results: int) -> List[Dict[str, Any]]:
        """从Bing搜索新闻"""
        try:
            params = config["params"].copy()
            params["q"] = keyword
            
            response = requests.get(
                config["base_url"], 
                params=params, 
                headers=config["headers"],
                timeout=10
            )
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            news_items = []
            
            # 解析Bing新闻结果
            news_elements = soup.find_all('div', class_='news-card')
            
            for element in news_elements[:max_results]:
                try:
                    # 提取标题
                    title_elem = element.find('h2')
                    if not title_elem:
                        continue
                    title = title_elem.get_text().strip()
                    
                    # 提取链接
                    link_elem = element.find('a')
                    if not link_elem:
                        continue
                    link = link_elem.get('href', '')
                    
                    # 提取摘要
                    summary_elem = element.find('p')
                    summary = summary_elem.get_text().strip() if summary_elem else ""
                    
                    # 提取来源和时间
                    source_elem = element.find('span', class_='source')
                    source = source_elem.get_text().strip() if source_elem else "Bing搜索"
                    
                    time_elem = element.find('span', class_='time')
                    publish_time = time_elem.get_text().strip() if time_elem else ""
                    
                    if title and link:
                        news_items.append({
                            "title": title,
                            "link": link,
                            "summary": summary,
                            "source": source,
                            "publish_time": publish_time,
                            "category": "自定义搜索",
                            "search_keyword": keyword
                        })
                except Exception as e:
                    logger.warning(f"解析Bing新闻项失败: {e}")
                    continue
            
            return news_items
            
        except Exception as e:
            logger.error(f"Bing搜索失败: {e}")
            return []
    
    def _deduplicate_news(self, news_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """去重新闻"""
        unique_news = {}
        for news in news_list:
            title = news.get("title", "").strip().lower()
            if title and title not in unique_news:
                unique_news[title] = news
        return list(unique_news.values())
    
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
                # 如果所有格式都失败，使用email.utils的时间解析
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
    
    def save_news(self, news_list: List[Dict[str, Any]], keyword: str) -> None:
        """保存搜索到的新闻"""
        if not news_list:
            logger.warning("没有新闻数据需要保存")
            return
        
        # 创建文件名
        safe_keyword = re.sub(r'[^\w\s-]', '', keyword).strip()
        safe_keyword = re.sub(r'[-\s]+', '_', safe_keyword)
        filename = f"custom_search_{safe_keyword}_{int(time.time())}.json"
        
        # 保存路径
        raw_file_path = self.data_dir / "raw" / filename
        raw_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 保存数据
        with open(raw_file_path, "w", encoding="utf-8") as f:
            json.dump(news_list, f, ensure_ascii=False, indent=2)
        
        logger.success(f"✅ 已保存 {len(news_list)} 条新闻到 {raw_file_path}")
    
    def run_custom_search(self, keyword: str, max_results: int = 80) -> List[Dict[str, Any]]:
        """运行自定义搜索流程"""
        logger.info(f"🚀 开始自定义搜索: {keyword}")
        
        # 1. 搜索新闻
        news_list = self.search_news(keyword, max_results)
        
        if not news_list:
            logger.warning("⚠️ 未找到相关新闻，创建示例数据")
            news_list = self._create_sample_news(keyword)
        
        # 2. 保存数据
        self.save_news(news_list, keyword)
        
        logger.success(f"🎉 自定义搜索完成！共获取 {len(news_list)} 条新闻")
        return news_list
    
    def _create_sample_news(self, keyword: str) -> List[Dict[str, Any]]:
        """创建示例新闻数据"""
        sample_news = [
            {
                "title": f"{keyword}相关新闻：市场动态分析",
                "link": f"https://example.com/news1",
                "summary": f"关于{keyword}的最新市场动态和发展趋势分析。",
                "source": "示例数据源",
                "publish_time": "2024-10-24",
                "category": "自定义搜索",
                "search_keyword": keyword
            },
            {
                "title": f"{keyword}行业报告：投资机会分析",
                "link": f"https://example.com/news2",
                "summary": f"深入分析{keyword}行业的投资机会和风险因素。",
                "source": "示例数据源",
                "publish_time": "2024-10-24",
                "category": "自定义搜索",
                "search_keyword": keyword
            },
            {
                "title": f"{keyword}技术发展：创新突破",
                "link": f"https://example.com/news3",
                "summary": f"{keyword}领域的技术创新和突破性进展。",
                "source": "示例数据源",
                "publish_time": "2024-10-24",
                "category": "自定义搜索",
                "search_keyword": keyword
            }
        ]
        
        logger.info(f"📝 已创建 {len(sample_news)} 条示例数据")
        return sample_news
