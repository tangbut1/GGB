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

        # ── 第 1 层：Google News RSS（最稳定，无需 API Key）──
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
        if len(aggregated) < target_results:
            logger.info("📡 [Layer 3/3] Bing 通用抓取补充...")
            remaining = target_results - len(aggregated)
            bing_results = self._search_generic(keyword, remaining=remaining)
            aggregated.extend(bing_results)
            logger.info("   Bing 抓取 → {} 条", len(bing_results))

        # ── 第 4 层：备选源 NewsAPI (如果配置了) ──
        import os
        newsapi_key = os.environ.get("NEWSAPI_KEY")
        if newsapi_key and len(aggregated) < target_results:
            logger.info("📡 [Layer 4/4] NewsAPI 备选源补充...")
            remaining = target_results - len(aggregated)
            newsapi_results = self._search_newsapi(keyword, remaining, newsapi_key)
            aggregated.extend(newsapi_results)
            logger.info("   NewsAPI 抓取 → {} 条", len(newsapi_results))

        # ── 辅助关键词扩大搜索（时间分布 + 关键词变体）──
        now = datetime.now()
        auxiliary_terms = [
            f"{keyword} 最新",
            f"{keyword} 新闻",
        ]
        # 时间维度扩展：最近 3 个月按月搜索，打破 "只有当天" 的限制
        for months_back in [1, 2, 3]:
            month_date = now - timedelta(days=months_back * 30)
            auxiliary_terms.append(
                f"{keyword} {month_date.year}年{month_date.month}月"
            )
        for term in auxiliary_terms:
            if len(aggregated) >= target_results:
                break
            per_term = min(40, max(20, (target_results - len(aggregated)) // len(auxiliary_terms) + 10))
            logger.info("🔍 辅助关键词搜索: {}", term)
            aggregated.extend(
                self._search_google_news(term, max_results=per_term)
            )

        if not aggregated:
            logger.warning("⚠️ 所有搜索源均未返回结果，请检查网络连接")
            return []

        deduplicated = self._deduplicate_news(aggregated)
        self._enrich_news_content(deduplicated)

        for item in deduplicated:
            publish_dt = item.pop("_publish_dt", None)
            if isinstance(publish_dt, datetime):
                item["publish_time"] = publish_dt.strftime("%Y-%m-%d %H:%M")

        deduplicated.sort(key=lambda x: x.get("publish_time", ""), reverse=True)
        logger.success("🎉 搜索完成！共获取 {} 条相关新闻（3 层回退）", len(deduplicated))
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

        logger.success("✅ 已保存 {} 条新闻到 {}", len(news_list), raw_file_path)

    # ------------------------------------------------------------------
    # DuckDuckGo search with retry
    # ------------------------------------------------------------------
    def _search_duckduckgo(self, keyword: str, max_results: int = 50, retries: int = 3) -> List[Dict[str, Any]]:
        """使用 DuckDuckGo 新闻搜索接口，带重试机制。"""
        results: List[Dict[str, Any]] = []

        if DDGS is None:
            logger.warning("DuckDuckGo 搜索不可用（ddgs 包未安装），跳过在线搜索。")
            return results

        for attempt in range(1, retries + 1):
            try:
                # 第 1 次尝试不带 region 限制，扩大搜索范围
                region = None if attempt <= 1 else "cn-zh"
                logger.info("使用 DuckDuckGo 搜索 {}（第 {} 次尝试，region={}）", keyword, attempt, region or "无限制")
                with DDGS(timeout=15 + attempt * 5) as ddgs:
                    kwargs = dict(
                        keywords=keyword,
                        safesearch="moderate",
                        max_results=max_results,
                    )
                    if region:
                        kwargs["region"] = region
                    for item in ddgs.news(**kwargs):
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
                if results:
                    break  # 成功获取结果，退出重试
            except Exception as exc:
                logger.warning("DuckDuckGo 搜索第 {} 次失败: {}", attempt, exc)
                if attempt < retries:
                    time.sleep(attempt * 1.5)
                else:
                    logger.error("❌ DuckDuckGo 搜索全部 {} 次尝试失败", retries)
        return results

    # ------------------------------------------------------------------
    # Google News RSS search (most reliable, no API key needed)
    # ------------------------------------------------------------------
    def _search_google_news(self, keyword: str, max_results: int = 50) -> List[Dict[str, Any]]:
        """通过 Google News RSS 搜索新闻，稳定且无需 API Key。"""
        import urllib.parse
        from xml.etree import ElementTree

        results: List[Dict[str, Any]] = []
        encoded_q = urllib.parse.quote(keyword)

        # 尝试中英文两种区域配置
        region_configs = [
            ("zh-CN", "CN", "CN:zh-Hans"),
            ("en-US", "US", "US:en"),
        ]

        for hl, gl, ceid in region_configs:
            if len(results) >= max_results:
                break
            
            for attempt in range(1, 4):
                try:
                    rss_url = (
                        f"https://news.google.com/rss/search"
                        f"?q={encoded_q}&hl={hl}&gl={gl}&ceid={ceid}"
                    )
                    logger.info("Google News RSS 搜索: {} (hl={}) (尝试 {})", keyword, hl, attempt)
                    resp = self.session.get(rss_url, timeout=self.search_timeout)
                    if resp.status_code != 200:
                        logger.warning("Google News RSS 返回 {}: {}", resp.status_code, hl)
                        if attempt < 3:
                            time.sleep(1.5 ** attempt)
                        continue
    
                    root = ElementTree.fromstring(resp.text)
                    for item_elem in root.iter("item"):
                        title = ""
                        link = ""
                        pub_date = ""
                        source = ""
                        description = ""

                        for child in item_elem:
                            tag = child.tag.lower() if hasattr(child, 'tag') else ''
                            if tag == "title":
                                title = (child.text or "").strip()
                            elif tag == "link":
                                link = (child.text or "").strip()
                            elif tag == "pubdate":
                                pub_date = (child.text or "").strip()
                            elif tag == "source":
                                source = (child.text or "").strip()
                            elif tag == "description":
                                description = (child.text or "").strip()

                        if not title:
                            continue

                        # title 格式: "新闻标题 - 来源名"
                        if " - " in title and not source:
                            parts = title.rsplit(" - ", 1)
                            title, source = parts[0].strip(), parts[1].strip()

                        # 从 description HTML 提取原始链接
                        orig_link = link
                        if description:
                            import re
                            href_match = re.search(r'href="(https?://[^"]+)"', description)
                            if href_match and "news.google.com" not in href_match.group(1):
                                orig_link = href_match.group(1)
                            # 提取纯文本摘要
                            clean_desc = re.sub(r'<[^>]+>', '', description)
                            clean_desc = re.sub(r'\s+', ' ', clean_desc).strip()[:300]
                        else:
                            clean_desc = ""

                        publish_dt = self._parse_datetime(pub_date) or datetime.now()

                        results.append({
                            "title": title,
                            "original_title": title,
                            "link": orig_link or link,
                            "summary": clean_desc,
                            "source": source or "Google News",
                            "publish_time": pub_date,
                            "category": "新闻搜索",
                            "search_keyword": keyword,
                            "_publish_dt": publish_dt,
                        })

                        if len(results) >= max_results:
                            break

                    if results:
                        logger.success("Google News RSS 获取 {} 条结果 (hl={})", len(results), hl)
                        break

                except Exception as exc:
                    logger.warning("Google News RSS 搜索失败 (hl={}, attempt={}): {}", hl, attempt, exc)
                    if attempt < 3:
                        time.sleep(1.5 ** attempt)
                    continue
            
            if results:
                break

        return results

    # ------------------------------------------------------------------
    # Generic fallback
    # ------------------------------------------------------------------
    def _search_generic(self, keyword: str, remaining: int) -> List[Dict[str, Any]]:
        """Bing News 网页抓取回退方案，多选择器兼容。"""
        if remaining <= 0:
            return []

        logger.info("尝试通过 Bing News HTML 抓取补充搜索结果...")
        url = "https://www.bing.com/news/search"
        params = {"q": keyword, "mkt": "zh-CN", "count": str(min(remaining, 30))}
        items: List[Dict[str, Any]] = []

        for attempt in range(1, 4):
            try:
                resp = self.session.get(url, params=params, timeout=self.search_timeout)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                # 多套选择器，兼容 Bing 不同的页面结构
                cards = []
                for selector in [
                    "div.news-card", "div.card-without-image", ".news-card",
                    "article", "div.t_s", "div.newsitem", "a[href*='articles']",
                ]:
                    cards = soup.select(selector)
                    if cards:
                        break

                if not cards:
                    # 最后尝试：找所有包含 /news/ 的链接
                    all_links = soup.find_all("a", href=True)
                    cards = [a for a in all_links if "/news/" in a.get("href", "") or "/articles/" in a.get("href", "")]
                    # 取前 10 个不同标题的
                    seen = set()
                    cards = [c for c in cards if not (c.get_text(strip=True) in seen or seen.add(c.get_text(strip=True)))][:min(remaining, 30)]

                for element in cards:
                    # 标题提取
                    title_elem = (
                        element.select_one("a.title") or
                        element.select_one("a[href]") or
                        (element if element.name == "a" else None)
                    )
                    if not title_elem:
                        continue

                    title = title_elem.get_text(strip=True)
                    link = title_elem.get("href", "")
                    if not title or not link or len(title) < 5:
                        continue
                    if not link.startswith("http"):
                        if link.startswith("/"):
                            link = "https://www.bing.com" + link
                        else:
                            continue

                    # 摘要提取
                    summary = ""
                    for sel in ["div.snippet", "div.snippet span", "p", "div.news_snippet", ".snippet"]:
                        s_elem = element.select_one(sel)
                        if s_elem:
                            summary = s_elem.get_text(strip=True)[:300]
                            break

                    # 来源提取
                    source = "Bing News"
                    for sel in ["div.source", "div.source span", "span.source", ".source", "div.news-source"]:
                        src_elem = element.select_one(sel)
                        if src_elem:
                            source = src_elem.get_text(strip=True)
                            break

                    # 时间提取
                    publish_time = ""
                    for sel in ["span.time", "time", ".time", "span.news-dt"]:
                        t_elem = element.select_one(sel)
                        if t_elem:
                            publish_time = t_elem.get_text(strip=True)
                            break

                    publish_dt = self._parse_datetime(publish_time) or datetime.now()

                    items.append({
                        "title": title,
                        "original_title": title,
                        "link": link,
                        "summary": summary,
                        "source": source,
                        "publish_time": publish_time,
                        "category": "新闻搜索",
                        "search_keyword": keyword,
                        "_publish_dt": publish_dt,
                    })

                    if len(items) >= remaining:
                        break

                if items:
                    break

            except Exception as exc:
                logger.error("Bing 网页抓取失败 (attempt={}): {}", attempt, exc)
                if attempt < 3:
                    time.sleep(1.5 ** attempt)

        return items

    def _search_newsapi(self, keyword: str, remaining: int, api_key: str) -> List[Dict[str, Any]]:
        """使用 NewsAPI 作为备选源。"""
        if remaining <= 0:
            return []
        
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": keyword,
            "apiKey": api_key,
            "pageSize": min(remaining, 50),
            "language": "zh",
            "from": (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
            "sortBy": "publishedAt"
        }
        items = []

        for attempt in range(1, 4):
            try:
                resp = self.session.get(url, params=params, timeout=self.search_timeout)
                if resp.status_code == 200:
                    articles = resp.json().get("articles", [])
                    for a in articles:
                        publish_dt = self._parse_datetime(a.get("publishedAt")) or datetime.now()
                        items.append({
                            "title": a.get("title", ""),
                            "original_title": a.get("title", ""),
                            "link": a.get("url", ""),
                            "summary": (a.get("description", "") or "")[:300],
                            "source": a.get("source", {}).get("name", "NewsAPI"),
                            "publish_time": a.get("publishedAt", ""),
                            "category": "新闻搜索",
                            "search_keyword": keyword,
                            "_publish_dt": publish_dt,
                        })
                    break
            except Exception as exc:
                logger.error("NewsAPI 搜索失败 (attempt={}): {}", attempt, exc)
                if attempt < 3:
                    time.sleep(1.5 ** attempt)
        
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
                    logger.debug("提取 {} 内容失败: {}", item.get("link"), exc)
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

        logger.info("📝 已创建 {} 条示例数据", len(sample_news))
        return sample_news


__all__ = ["CustomSearchCollector"]
