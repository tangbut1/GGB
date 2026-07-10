#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""自定义关键词搜索采集模块 — 多源冗余架构。

三层回退策略：
  1. Google News RSS（最稳定，无需 API Key，中英文均支持）
  2. DuckDuckGo News API（需要 ddgs/duckduckgo_search 包）
  3. Bing News HTML 抓取（多选择器兼容，最后兜底）

保证分析质量，模块会自动补充文章正文、摘要、发布时间等关键信息，
并将结果保存到 data/raw 目录。
"""

from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
try:
    from ddgs import DDGS
except ImportError:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        DDGS = None
from loguru import logger

UserAgent = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


class CustomSearchCollector:
    """自定义搜索新闻采集器 - 根据用户输入的关键词搜索相关新闻"""

    def __init__(self, max_workers: int = 4) -> None:
        self.data_dir = Path(__file__).resolve().parents[2] / "data"
        self.data_dir.mkdir(exist_ok=True)
        self.cutoff_date = datetime.now() - timedelta(days=90)
        self.max_workers = max_workers
        self.min_results = 30

        import os
        self.search_timeout = int(os.environ.get("MP_SEARCH_TIMEOUT", 15))

        # fix: 初始化 _google_banned 和 _bing_banned，避免首次调用时 AttributeError
        self._google_banned = False
        self._bing_banned = False

        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": UserAgent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Cache-Control": "no-cache",
            }
        )

    # ------------------------------------------------------------------
    # Public APIs
    # ------------------------------------------------------------------
    def run_custom_search(self, keyword: str, max_results: int = 120) -> List[Dict[str, Any]]:
        """运行完整的自定义搜索流程。"""
        logger.info("🚀 开始自定义搜索: {}", keyword)

        news_list = self.search_news(keyword, max_results=max_results)
        if not news_list:
            logger.error("❌ 未找到与 {} 相关的实时新闻，请尝试更换关键词。", keyword)
            return []

        self.save_news(news_list, keyword)
        logger.success("🎉 自定义搜索完成！共获取 {} 条新闻", len(news_list))
        if len(news_list) < self.min_results:
            logger.warning(
                "⚠️ 搜索结果仅 {} 条，未达到 {} 条目标，建议尝试更具体或更广泛的关键词组合。",
                len(news_list),
                self.min_results,
            )
        return news_list

    def search_news(self, keyword: str, max_results: int = 120) -> List[Dict[str, Any]]:
        """根据关键词搜索新闻并做预处理 — 多源冗余回退。"""
        logger.info("🔍 开始搜索关键词: {}", keyword)
        aggregated: List[Dict[str, Any]] = []
        target_results = max(max_results, self.min_results)

        # ── 第 1 层：Google News RSS ──
        if not self._google_banned:
            logger.info("📡 [Layer 1/3] Google News RSS 搜索...")
            google_results = self._search_google_news(keyword, max_results=target_results)
            aggregated.extend(google_results)
            logger.info("   Google News RSS → {} 条", len(google_results))

        # ── 第 2 层：DuckDuckGo 补充 ──
        if len(aggregated) < target_results:
            logger.info("📡 [Layer 2/3] DuckDuckGo 搜索补充...")
            remaining = target_results - len(aggregated)
            ddg_results = self._search_duckduckgo(keyword, max_results=remaining)
            aggregated.extend(ddg_results)
            logger.info("   DuckDuckGo → {} 条", len(ddg_results))

        # ── 第 3 层：Bing/通用网页抓取 ──
        if len(aggregated) < target_results and not self._bing_banned:
            logger.info("📡 [Layer 3/3] Bing 通用抓取补充...")
            remaining = target_results - len(aggregated)
            bing_results = self._search_generic(keyword, remaining=remaining)
            aggregated.extend(bing_results)
            logger.info("   Bing 抓取 → {} 条", len(bing_results))

        # ── 第 4 层：备选源 NewsAPI ──
        import os
        newsapi_key = os.environ.get("NEWSAPI_KEY")
        if newsapi_key and len(aggregated) < target_results:
            logger.info("📡 [Layer 4/4] NewsAPI 备选源补充...")
            remaining = target_results - len(aggregated)
            newsapi_results = self._search_newsapi(keyword, remaining, newsapi_key)
            aggregated.extend(newsapi_results)
            logger.info("   NewsAPI 抓取 → {} 条", len(newsapi_results))

        # ── 辅助关键词扩大搜索 ──
        now = datetime.now()
        auxiliary_terms = [
            f"{keyword} 最新",
            f"{keyword} 新闻",
        ]
        for months_back in [1, 2, 3]:
            d = now.replace(day=1) - timedelta(days=months_back * 28)
            auxiliary_terms.append(f"{keyword} {d.year}年{d.month}月")

        for term in auxiliary_terms:
            if len(aggregated) >= target_results:
                break
            if not self._google_banned:
                extra = self._search_google_news(term, max_results=20)
                aggregated.extend(extra)

        # 去重（按 link）
        seen_urls: set = set()
        deduped: List[Dict[str, Any]] = []
        for item in aggregated:
            url = item.get("link", "") or item.get("url", "")
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            deduped.append(item)

        return deduped[:target_results]

    def save_news(self, news_list: List[Dict[str, Any]], keyword: str) -> None:
        """将采集结果保存到 data/raw 目录。"""
        raw_dir = self.data_dir / "raw"
        raw_dir.mkdir(exist_ok=True)
        safe_kw = re.sub(r'[^\w\-]', '_', keyword)[:40]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = raw_dir / f"custom_{safe_kw}_{timestamp}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(news_list, f, ensure_ascii=False, indent=2, default=str)
        logger.info("💾 已保存 {} 条新闻到 {}", len(news_list), out_path)

    # ------------------------------------------------------------------
    # Internal search backends
    # ------------------------------------------------------------------
    def _search_google_news(self, keyword: str, max_results: int = 60) -> List[Dict[str, Any]]:
        """Google News RSS 搜索。"""
        results: List[Dict[str, Any]] = []
        try:
            import urllib.parse
            query = urllib.parse.quote(keyword)
            urls = [
                f"https://news.google.com/rss/search?q={query}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
                f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en",
            ]
            for rss_url in urls:
                if len(results) >= max_results:
                    break
                try:
                    resp = self.session.get(rss_url, timeout=self.search_timeout)
                    resp.raise_for_status()
                    soup = BeautifulSoup(resp.content, "xml")
                    items = soup.find_all("item")
                    for item in items:
                        if len(results) >= max_results:
                            break
                        title = item.find("title")
                        link = item.find("link")
                        pub_date = item.find("pubDate")
                        source = item.find("source")
                        description = item.find("description")
                        results.append({
                            "title": title.text if title else "",
                            "link": link.text if link else "",
                            "publish_time": pub_date.text if pub_date else "",
                            "source": source.text if source else "Google News",
                            "summary": BeautifulSoup(description.text, "html.parser").get_text() if description else "",
                            "category": "news",
                        })
                except Exception as e:
                    logger.warning("Google RSS {} 失败: {}", rss_url, e)
        except Exception as e:
            logger.warning("Google News RSS 整体失败: {}", e)
            self._google_banned = True
        return results

    def _search_duckduckgo(self, keyword: str, max_results: int = 40) -> List[Dict[str, Any]]:
        """DuckDuckGo News 搜索。"""
        if DDGS is None:
            return []
        results: List[Dict[str, Any]] = []
        try:
            with DDGS() as ddgs:
                for r in ddgs.news(keyword, max_results=max_results):
                    results.append({
                        "title": r.get("title", ""),
                        "link": r.get("url", ""),
                        "publish_time": r.get("date", ""),
                        "source": r.get("source", "DuckDuckGo"),
                        "summary": r.get("body", ""),
                        "category": "news",
                    })
        except Exception as e:
            logger.warning("DuckDuckGo 搜索失败: {}", e)
        return results

    def _search_generic(self, keyword: str, remaining: int = 30) -> List[Dict[str, Any]]:
        """Bing News HTML 抓取。"""
        import urllib.parse
        results: List[Dict[str, Any]] = []
        try:
            query = urllib.parse.quote(keyword)
            url = f"https://www.bing.com/news/search?q={query}&count={remaining}"
            resp = self.session.get(url, timeout=self.search_timeout)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            selectors = [
                ("div.news-card", "a.title", "span.source", "span.datetime"),
                ("div.newsitem", "a", "span.source", "span.time"),
                ("div[class*='news']", "a[href]", "span", "span"),
            ]
            for card_sel, title_sel, src_sel, time_sel in selectors:
                cards = soup.select(card_sel)
                if not cards:
                    continue
                for card in cards:
                    if len(results) >= remaining:
                        break
                    title_el = card.select_one(title_sel)
                    src_el = card.select_one(src_sel)
                    time_el = card.select_one(time_sel)
                    if not title_el:
                        continue
                    results.append({
                        "title": title_el.get_text(strip=True),
                        "link": title_el.get("href", ""),
                        "publish_time": time_el.get_text(strip=True) if time_el else "",
                        "source": src_el.get_text(strip=True) if src_el else "Bing News",
                        "summary": "",
                        "category": "news",
                    })
                if results:
                    break
        except Exception as e:
            logger.warning("Bing 抓取失败: {}", e)
            self._bing_banned = True
        return results

    def _search_newsapi(self, keyword: str, max_results: int, api_key: str) -> List[Dict[str, Any]]:
        """NewsAPI.org 备选源。"""
        results: List[Dict[str, Any]] = []
        try:
            url = "https://newsapi.org/v2/everything"
            params = {
                "q": keyword,
                "pageSize": min(max_results, 100),
                "sortBy": "publishedAt",
                "apiKey": api_key,
            }
            resp = self.session.get(url, params=params, timeout=self.search_timeout)
            resp.raise_for_status()
            data = resp.json()
            for article in data.get("articles", []):
                results.append({
                    "title": article.get("title", ""),
                    "link": article.get("url", ""),
                    "publish_time": article.get("publishedAt", ""),
                    "source": (article.get("source") or {}).get("name", "NewsAPI"),
                    "summary": article.get("description", ""),
                    "category": "news",
                })
        except Exception as e:
            logger.warning("NewsAPI 搜索失败: {}", e)
        return results
