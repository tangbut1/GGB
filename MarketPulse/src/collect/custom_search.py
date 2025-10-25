#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""自定义关键词搜索采集模块。

该版本使用 DuckDuckGo 的新闻检索接口模拟真实浏览器搜索，并在必要时
回退到传统的网页抓取。为保证分析质量，模块会自动补充文章正文、摘要、
发布时间等关键信息，并将结果保存到 data/raw 目录。
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
from duckduckgo_search import DDGS
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
        self.cutoff_date = datetime.now() - timedelta(days=3)
        self.max_workers = max_workers
        self.min_results = 100

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
        logger.info("🚀 开始自定义搜索: %s", keyword)

        news_list = self.search_news(keyword, max_results=max_results)
        if not news_list:
            logger.error("❌ 未找到与 %s 相关的实时新闻，请尝试更换关键词。", keyword)
            return []

        self.save_news(news_list, keyword)
        logger.success("🎉 自定义搜索完成！共获取 %s 条新闻", len(news_list))
        if len(news_list) < self.min_results:
            logger.warning(
                "⚠️ 搜索结果仅 %s 条，未达到 %s 条目标，建议尝试更具体或更广泛的关键词组合。",
                len(news_list),
                self.min_results,
            )
        return news_list

    def search_news(self, keyword: str, max_results: int = 120) -> List[Dict[str, Any]]:
        """根据关键词搜索新闻并做预处理。"""
        logger.info("🔍 开始搜索关键词: %s", keyword)
        aggregated: List[Dict[str, Any]] = []
        target_results = max(max_results, self.min_results)

        primary_terms = [keyword]
        auxiliary_terms = [
            f"{keyword} 最新",
            f"{keyword} 新闻",
            f"{keyword} 市场",
            f"{keyword} 趋势",
        ]

        for term in primary_terms + [t for t in auxiliary_terms if t not in primary_terms]:
            ddg_results = self._search_duckduckgo(term, max_results=target_results)
            aggregated.extend(ddg_results)
            if len(aggregated) >= target_results:
                break

        if len(aggregated) < target_results:
            logger.info("DuckDuckGo 结果不足，尝试补充通用网页抓取...")
            aggregated.extend(self._search_generic(keyword, remaining=target_results - len(aggregated)))

        if len(aggregated) < target_results:
            for term in auxiliary_terms:
                if len(aggregated) >= target_results:
                    break
                aggregated.extend(self._search_generic(term, remaining=target_results - len(aggregated)))

        if not aggregated:
            return []

        deduplicated = self._deduplicate_news(aggregated)
        self._enrich_news_content(deduplicated)

        for item in deduplicated:
            publish_dt = item.pop("_publish_dt", None)
            if isinstance(publish_dt, datetime):
                item["publish_time"] = publish_dt.strftime("%Y-%m-%d %H:%M")

        deduplicated.sort(key=lambda x: x.get("publish_time", ""), reverse=True)
        logger.success("🎉 搜索完成！共获取 %s 条相关新闻", len(deduplicated))
        return deduplicated[:target_results]

    def save_news(self, news_list: List[Dict[str, Any]], keyword: str) -> None:
        """保存搜索到的新闻数据到本地 JSON 文件。"""
        if not news_list:
            logger.warning("没有新闻数据需要保存")
            return

        safe_keyword = re.sub(r"[^\w\s-]", "", keyword).strip()
        safe_keyword = re.sub(r"[-\s]+", "_", safe_keyword)
        filename = f"custom_search_{safe_keyword}_{int(time.time())}.json"

        raw_file_path = self.data_dir / "raw" / filename
        raw_file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(raw_file_path, "w", encoding="utf-8") as f:
            json.dump(news_list, f, ensure_ascii=False, indent=2)

        logger.success("✅ 已保存 %s 条新闻到 %s", len(news_list), raw_file_path)

    # ------------------------------------------------------------------
    # DuckDuckGo search
    # ------------------------------------------------------------------
    def _search_duckduckgo(self, keyword: str, max_results: int = 50) -> List[Dict[str, Any]]:
        """使用 DuckDuckGo 新闻搜索接口。"""
        results: List[Dict[str, Any]] = []
        try:
            logger.info("使用 DuckDuckGo 搜索 %s", keyword)
            with DDGS(timeout=20) as ddgs:
                for item in ddgs.news(
                    keywords=keyword,
                    region="cn-zh",
                    safesearch="moderate",
                    max_results=max_results,
                ):
                    title = (item.get("title") or "").strip()
                    url = (item.get("url") or item.get("link") or "").strip()
                    if not title or not url:
                        continue

                    publish_dt = self._parse_datetime(item.get("date"))
                    if publish_dt and publish_dt < self.cutoff_date:
                        continue

                    summary = (item.get("body") or "").strip()
                    source = (item.get("source") or "DuckDuckGo").strip()

                    results.append(
                        {
                            "title": title,
                            "original_title": title,
                            "link": url,
                            "summary": summary,
                            "source": source or "DuckDuckGo",
                            "publish_time": item.get("date", ""),
                            "category": "自定义搜索",
                            "search_keyword": keyword,
                            "_publish_dt": publish_dt or datetime.now(),
                        }
                    )
        except Exception as exc:  # noqa: BLE001
            logger.error("❌ DuckDuckGo 搜索失败: %s", exc)
        return results

    # ------------------------------------------------------------------
    # Generic fallback
    # ------------------------------------------------------------------
    def _search_generic(self, keyword: str, remaining: int) -> List[Dict[str, Any]]:
        """简单的网页抓取回退方案，模拟浏览器搜索结果页。"""
        if remaining <= 0:
            return []

        logger.info("尝试通过 HTML 抓取补充搜索结果...")
        url = "https://www.bing.com/news/search"
        params = {"q": keyword, "mkt": "zh-CN", "count": str(min(remaining, 30))}
        items: List[Dict[str, Any]] = []

        try:
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            for element in soup.select("div.news-card"):
                title_elem = element.select_one("a.title") or element.select_one("a")
                if not title_elem:
                    continue

                title = title_elem.get_text(strip=True)
                link = title_elem.get("href", "")
                if not title or not link:
                    continue

                summary_elem = element.select_one("div.snippet") or element.select_one("div.snippet span")
                summary = summary_elem.get_text(strip=True) if summary_elem else ""

                source_elem = element.select_one("div.source") or element.select_one("div.source span")
                source = source_elem.get_text(strip=True) if source_elem else "Bing 新闻"

                time_elem = element.select_one("span.time")
                publish_time = time_elem.get_text(strip=True) if time_elem else ""

                publish_dt = self._parse_datetime(publish_time) or datetime.now()
                if publish_dt < self.cutoff_date:
                    continue

                items.append(
                    {
                        "title": title,
                        "original_title": title,
                        "link": link,
                        "summary": summary,
                        "source": source,
                        "publish_time": publish_time,
                        "category": "自定义搜索",
                        "search_keyword": keyword,
                        "_publish_dt": publish_dt,
                    }
                )
        except Exception as exc:  # noqa: BLE001
            logger.error("通用网页抓取失败: %s", exc)

        return items

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _enrich_news_content(self, news_items: List[Dict[str, Any]]) -> None:
        """为搜索结果补充正文和摘要信息。"""
        if not news_items:
            return

        tasks = [item for item in news_items if item.get("link")]
        if not tasks:
            return

        max_items = min(len(tasks), 12)
        selected = tasks[:max_items]

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_map = {
                executor.submit(self._extract_article_text, item["link"]): item for item in selected
            }

            for future in as_completed(future_map):
                item = future_map[future]
                try:
                    content, summary = future.result()
                except Exception as exc:  # noqa: BLE001
                    logger.debug("提取 %s 内容失败: %s", item.get("link"), exc)
                    continue

                if content:
                    item["content"] = content
                if summary and not item.get("summary"):
                    item["summary"] = summary

    def _extract_article_text(self, url: str) -> Tuple[str, str]:
        """从文章页面中提取正文与摘要。"""
        resp = self.session.get(url, timeout=15)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        paragraphs = [p for p in paragraphs if p]
        if not paragraphs:
            return "", ""

        text = "\n".join(paragraphs)
        text = re.sub(r"\s+", " ", text).strip()

        # 生成摘要
        summary = "".join(paragraphs[:3])
        summary = summary[:280] + ("..." if len(summary) > 280 else "")
        content = text[:5000]
        return content, summary

    def _parse_datetime(self, value: Optional[str]) -> Optional[datetime]:
        """解析多种来源的时间字符串。"""
        if not value:
            return None

        if isinstance(value, datetime):
            return value if value.tzinfo is None else value.replace(tzinfo=None)

        value = str(value).strip()
        if not value:
            return None

        # DuckDuckGo 返回 ISO 字符串，处理 Z 结尾
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"

        iso_formats = (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%Y/%m/%d %H:%M",
            "%Y.%m.%d %H:%M",
        )

        try:
            dt = datetime.fromisoformat(value)
            return dt.replace(tzinfo=None)
        except Exception:  # noqa: BLE001
            pass

        for fmt in iso_formats:
            try:
                return datetime.strptime(value, fmt)
            except Exception:  # noqa: BLE001
                continue

        # 处理类似 “3小时前” 的相对时间
        relative = re.match(r"(\d+)(分钟|小时|天)前", value)
        if relative:
            amount = int(relative.group(1))
            unit = relative.group(2)
            delta = {
                "分钟": timedelta(minutes=amount),
                "小时": timedelta(hours=amount),
                "天": timedelta(days=amount),
            }.get(unit, timedelta())
            return datetime.now() - delta

        return None

    def _deduplicate_news(self, news_list: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """按链接优先去重，保留不同来源的重复标题。"""
        unique: Dict[str, Dict[str, Any]] = {}
        for news in news_list:
            title = (news.get("title") or "").strip().lower()
            link = (news.get("link") or news.get("url") or "").strip().lower()
            source = (news.get("source") or "").strip().lower()
            if not title and not link:
                continue
            key = link if link else f"{title}::{source}"
            if key not in unique:
                unique[key] = news
        return list(unique.values())

    def _create_sample_news(self, keyword: str) -> List[Dict[str, Any]]:
        """创建示例新闻数据。"""
        today = datetime.now().strftime("%Y-%m-%d")
        sample_news = [
            {
                "title": f"{keyword} 相关新闻：市场动态分析",
                "link": "https://example.com/news1",
                "summary": f"关于 {keyword} 的最新市场动态和发展趋势分析。",
                "source": "示例数据源",
                "publish_time": today,
                "category": "自定义搜索",
                "search_keyword": keyword,
                "content": f"这是一条关于 {keyword} 的示例新闻，用于在真实数据缺失时展示应用流程。",
            },
            {
                "title": f"{keyword} 行业报告：投资机会分析",
                "link": "https://example.com/news2",
                "summary": f"深入分析 {keyword} 行业的投资机会和风险因素。",
                "source": "示例数据源",
                "publish_time": today,
                "category": "自定义搜索",
                "search_keyword": keyword,
                "content": f"示例新闻展示 {keyword} 在行业中的投资亮点与潜在风险。",
            },
            {
                "title": f"{keyword} 技术发展：创新突破",
                "link": "https://example.com/news3",
                "summary": f"{keyword} 领域的技术创新和突破性进展。",
                "source": "示例数据源",
                "publish_time": today,
                "category": "自定义搜索",
                "search_keyword": keyword,
                "content": f"该示例新闻描述了 {keyword} 相关的新技术与行业趋势。",
            },
        ]

        logger.info("📝 已创建 %s 条示例数据", len(sample_news))
        return sample_news


__all__ = ["CustomSearchCollector"]
