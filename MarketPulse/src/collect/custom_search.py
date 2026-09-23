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
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from xml.etree import ElementTree

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

from ..net_safety import validate_public_url, safe_output_path

# RSS 响应体上限。Google News 一次搜索的正常响应在 100KB 上下，
# 给到 4MB 仍宽裕；再大只可能是异常响应，没必要喂给解析器。
RSS_MAX_BYTES = 4 * 1024 * 1024


def parse_rss(text: str):
    """解析第三方 RSS，解析前先挡掉 DTD 实体扩展。

    ElementTree 默认接受内部 DTD 实体声明，一个层层嵌套实体的 feed
    （billion laughs）就能把内存吃光。搜索引擎返回的 XML 和搜索结果一样
    属于不可信输入，所以 DOCTYPE/ENTITY 直接拒，超长也直接拒——宁可用不了
    这个源，也不能让一次采集把进程拖死。
    """
    if not text or len(text) > RSS_MAX_BYTES:
        raise ValueError("RSS 响应体为空或超过大小上限")
    lowered = text.lower()
    if "<!doctype" in lowered or "<!entity" in lowered:
        raise ValueError("RSS 含 DTD 实体声明，已拒绝解析")
    return ElementTree.fromstring(text)


UserAgent = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# Bing 新闻页顶部的时间/排序筛选器也是指向 /news/search 的链接，兜底的
# "包含 /news/ 的链接"扫描会把它们当成新闻卡片收进来，标题全是
# "Past hour"这类 UI 文案，进而污染情绪分析、来源分布和证据列表。
BING_UI_TITLES = {
    "past hour", "past 1 hour", "past 24 hours", "past 7 days",
    "past week", "past 30 days", "past month", "past year",
    "most recent", "most read", "any time", "latest",
    "sort by date", "sort by relevance", "all news", "local news",
    "videos", "images", "see more", "load more", "next", "previous",
}


def _is_bing_ui_link(href: str, title: str) -> bool:
    """判断一个 Bing 链接是筛选器/导航而不是新闻正文。"""
    href_l = (href or "").lower()
    if "/news/search" in href_l or "ftfilter" in href_l or "filters=" in href_l:
        return True
    return (title or "").strip().lower() in BING_UI_TITLES


class CustomSearchCollector:
    """自定义搜索新闻采集器 - 根据用户输入的关键词搜索相关新闻"""

    def __init__(self, max_workers: int = 4) -> None:
        self.data_dir = Path(__file__).resolve().parents[2] / "data"
        self.data_dir.mkdir(exist_ok=True)
        self.cutoff_date = datetime.now() - timedelta(days=90)
        self.max_workers = max_workers
        self.min_results = 30

        # 数据源熔断标志：命中 403/429/503 后短路，避免每轮重复踩被封来源
        self._google_banned = False
        self._bing_banned = False
        self._ddg_banned = False

        import os
        self.search_timeout = int(os.environ.get("MP_SEARCH_TIMEOUT", 15))
        # 采集阶段的总时间预算（秒）。搜索是多层回退 + 多辅助词的结构，
        # 单次请求都有 timeout，但叠加起来最坏能到十几分钟：期间界面一直
        # 停在"分析中"且没有任何反馈。超预算就带着已有结果进入分析。
        # 注意预算按采集器实例计算，不按单次 search_news 计算——一次采集
        # 会调用主搜索 + 多个补充词，每次都给全额预算等于没有预算。
        self.search_budget = float(os.environ.get("MP_SEARCH_BUDGET", 150))
        self._deadline: Optional[float] = None


        # 第三方客户端（duckduckgo_search 等）自带的 timeout 不一定覆盖
        # 连接建立的每个阶段，实测出现过挂住不返回、把整个采集阶段冻死
        # 几分钟的情况。设一个 socket 级兜底超时，保证任何网络读都有上限。
        socket.setdefaulttimeout(self.search_timeout)

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
    def run_custom_search(self, keyword: str, max_results: int = 120,
                          expand_auxiliary: bool = True) -> List[Dict[str, Any]]:
        """运行完整的自定义搜索流程。"""
        logger.info("🚀 开始自定义搜索: {}", keyword)

        news_list = self.search_news(keyword, max_results=max_results,
                                     expand_auxiliary=expand_auxiliary)
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

    def search_news(self, keyword: str, max_results: int = 120,
                    expand_auxiliary: bool = True) -> List[Dict[str, Any]]:
        """根据关键词搜索新闻并做预处理 — 多源冗余回退。

        expand_auxiliary=False 时只跑三层主搜索，不再自动追加月份/变体
        补充词。调用方自己给出差异化查询词时（CollectAgent 的补充采集）
        必须关掉：否则"宁德时代 报道"会再展开成"宁德时代 报道 最新"、
        "宁德时代 报道 2026年8月"，一次补充变成 6×5 次查询，绝大部分是
        拼出来的废词，只烧采集预算。
        """
        logger.info("🔍 开始搜索关键词: {}", keyword)
        aggregated: List[Dict[str, Any]] = []
        target_results = max(max_results, self.min_results)
        # 预算从本次采集的第一次搜索起算，补充词共享同一个截止时间
        if self._deadline is None:
            self._deadline = time.monotonic() + self.search_budget
        deadline = self._deadline

        def out_of_budget() -> bool:
            return time.monotonic() >= deadline

        # ── 第 1 层：Google News RSS（最稳定，无需 API Key）──
        # 先按"最新"拉一轮：舆情分析的价值几乎全在时效上，三小时前的快讯和
        # 三天前的快讯不能等权。24h 窗口拿不够量时再回落到 7d，避免为了凑数
        # 把一周前的旧闻当成"最新舆情"。
        if not out_of_budget():
            logger.info("📡 [Layer 1/3] Google News RSS 搜索...")
            fresh = self._search_google_news(
                keyword, max_results=target_results, deadline=deadline, when="1d")
            aggregated.extend(fresh)
            logger.info("   Google News RSS (24h 窗口) → {} 条", len(fresh))
            if len(aggregated) < target_results and not out_of_budget():
                recent = self._search_google_news(
                    keyword, max_results=target_results, deadline=deadline, when="7d")
                aggregated.extend(recent)
                logger.info("   Google News RSS (7d 窗口) → {} 条", len(recent))
        else:
            logger.warning("⏱ 已超出采集预算，跳过 Google News RSS")

        # ── 第 2 层：DuckDuckGo 补充 ──
        if not out_of_budget() and len(aggregated) < target_results:
            logger.info("📡 [Layer 2/3] DuckDuckGo 搜索补充...")
            remaining = target_results - len(aggregated)
            ddg_results = self._search_duckduckgo(keyword, max_results=remaining, deadline=deadline)
            aggregated.extend(ddg_results)
            logger.info("   DuckDuckGo → {} 条", len(ddg_results))
        elif len(aggregated) < target_results:
            logger.warning("⏱ 已超出采集预算，跳过 DuckDuckGo")

        # ── 第 3 层：Bing/通用网页抓取 ──
        if not out_of_budget() and len(aggregated) < target_results:
            logger.info("📡 [Layer 3/3] Bing 通用抓取补充...")
            remaining = target_results - len(aggregated)
            bing_results = self._search_generic(keyword, remaining=remaining, deadline=deadline)
            aggregated.extend(bing_results)
            logger.info("   Bing 抓取 → {} 条", len(bing_results))
        elif len(aggregated) < target_results:
            logger.warning("⏱ 已超出采集预算，跳过 Bing 抓取")

        # ── 第 4 层：备选源 NewsAPI (如果配置了) ──
        import os
        newsapi_key = os.environ.get("NEWSAPI_KEY")
        if newsapi_key and not out_of_budget() and len(aggregated) < target_results:
            logger.info("📡 [Layer 4/4] NewsAPI 备选源补充...")
            remaining = target_results - len(aggregated)
            newsapi_results = self._search_newsapi(keyword, remaining, newsapi_key)
            aggregated.extend(newsapi_results)
            logger.info("   NewsAPI 抓取 → {} 条", len(newsapi_results))

        # ── 辅助关键词扩大搜索（时间分布 + 关键词变体）──
        now = datetime.now()
        # 时间维度扩展：最近 3 个月按月搜索，打破 "只有当天" 的限制。
        # 这几个词与"够不够量"无关——它们负责把发布时间摊开到多天，
        # 否则按天序列只有一个点、趋势预测直接不可行。所以不能像
        # "最新/新闻"那样被数量门槛挡掉：Google 一轮返回 100 条原始结果时
        # aggregated 早已超过 target，月份词会被整体跳过，而原始结果里大量是
        # 同一事件的转载，去重后可能只剩几十条。月份词只受采集预算约束。
        month_terms = []
        for months_back in [1, 2, 3]:
            month_date = now - timedelta(days=months_back * 30)
            month_terms.append(
                f"{keyword} {month_date.year}年{month_date.month}月"
            )
        variant_terms = [f"{keyword} 最新", f"{keyword} 新闻"]
        skipped_terms = 0
        if expand_auxiliary:
            for term in month_terms + variant_terms:
                is_month = term in month_terms
                if not is_month and len(aggregated) >= target_results:
                    break
                if out_of_budget():
                    # 预算耗尽就停止追加搜索：带着已有结果进入分析，
                    # 好过把界面无限期停在"分析中"。
                    skipped_terms += 1
                    continue
                per_term = min(40, max(20, (target_results - len(aggregated)) // 5 + 10))
                logger.info("🔍 辅助关键词搜索: {} (when=90d)", term)
                # 月份补充词必须配宽窗口。默认 when=7d 时，"宁德时代 2026年8月"
                # 只会命中"最近一周发布、正文提到 8 月"的稿子，发布日全落在
                # 本周——按月搜索也就永远拿不到更早的样本。Google News RSS 的
                # 索引大约只回溯一个月，90d 已经能取到它愿意给的全部历史。
                aggregated.extend(
                    self._search_google_news(term, max_results=per_term,
                                             deadline=deadline, when="90d")
                )
            if skipped_terms:
                logger.warning("⏱ 采集预算用尽，{} 个辅助关键词未搜索，以已有 {} 条结果继续",
                               skipped_terms, len(aggregated))

        if not aggregated:
            logger.warning("⚠️ 所有搜索源均未返回结果，请检查网络连接")
            return []

        # 先把内部时间戳落成标准字符串。这一步必须在排序前：各来源的
        # publish_time 原始格式互不相同（RFC 822、ISO、美式日期），按字符串
        # 排会把 "8/29/2025" 排到 "2026-09-22" 后面去。
        for item in aggregated:
            publish_dt = item.pop("_publish_dt", None)
            if isinstance(publish_dt, datetime):
                item["publish_time"] = publish_dt.strftime("%Y-%m-%d %H:%M")

        # 最新的排在最前。下游（情绪分布、热词、证据流）取前 N 条时，排序
        # 决定了分析的是"最近"还是"随机一段"。
        aggregated.sort(key=lambda x: x.get("publish_time", ""), reverse=True)

        deduplicated = self._deduplicate_news(aggregated)
        # 标题签名去重放在排序之后：同一事件被多家转载时保留最新的那条。
        # 放在排序前会按搜索引擎的返回顺序留下旧稿。
        deduplicated = self._deduplicate_near_duplicates(deduplicated)
        deduplicated = self._annotate_sources(deduplicated)
        # 正文抓取放在去重之后：重复 URL 已经并掉，不必再为转载稿各拉一次页面
        self._enrich_news_content(deduplicated)

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

        # 上面两步已把关键词收敛成 [\w-]，但"清洗过"和"不可能穿越"是两回事：
        # 换一套正则、或者将来有人直接拿原始 keyword 拼名字，这里就漏了。
        # 以 data_dir 为基准再收敛一次，越界即拒绝。
        raw_file_path = safe_output_path(self.data_dir, "raw", filename)
        raw_file_path.parent.mkdir(parents=True, exist_ok=True)

        raw_file_path.write_text(
            json.dumps(news_list, ensure_ascii=False, indent=2),
            encoding="utf-8")

        logger.success("✅ 已保存 {} 条新闻到 {}", len(news_list), raw_file_path)

    # ------------------------------------------------------------------
    # DuckDuckGo search with retry
    # ------------------------------------------------------------------
    def _search_duckduckgo(self, keyword: str, max_results: int = 50, retries: int = 3,
                           deadline: Optional[float] = None) -> List[Dict[str, Any]]:
        """使用 DuckDuckGo 新闻搜索接口，带重试机制。"""
        results: List[Dict[str, Any]] = []

        if DDGS is None:
            logger.warning("DuckDuckGo 搜索不可用（ddgs 包未安装），跳过在线搜索。")
            return results

        # 同一轮采集里已经三次都连不上，就没必要让每个补充词再各烧 60 秒
        if self._ddg_banned:
            logger.info("DuckDuckGo 本轮已熔断，跳过")
            return results

        for attempt in range(1, retries + 1):
            # 预算耗尽就不再发起新请求：ddgs 自带的 timeout 不覆盖连接
            # 建立的每个阶段，单次调用可能挂住好几分钟。
            if deadline is not None and time.monotonic() >= deadline:
                logger.warning("⏱ 采集预算耗尽，DuckDuckGo 停止第 {} 次尝试", attempt)
                break
            try:
                # 第 1 次尝试不带 region 限制，扩大搜索范围
                region = None if attempt <= 1 else "cn-zh"
                logger.info("使用 DuckDuckGo 搜索 {}（第 {} 次尝试，region={}）", keyword, attempt, region or "无限制")
                with DDGS(timeout=15 + attempt * 5) as ddgs:
                    kwargs = dict(
                        keywords=keyword,
                        safesearch="moderate",
                        max_results=max_results,
                        timelimit="w"
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
                    logger.error("❌ DuckDuckGo 搜索全部 {} 次尝试失败，本轮熔断该源", retries)
                    self._ddg_banned = True
        return results

    # ------------------------------------------------------------------
    # Google News RSS search (most reliable, no API key needed)
    # ------------------------------------------------------------------
    def _search_google_news(self, keyword: str, max_results: int = 50,
                            deadline: Optional[float] = None,
                            when: str = "7d") -> List[Dict[str, Any]]:
        """通过 Google News RSS 搜索新闻，稳定且无需 API Key。

        when 是 Google News 的时间窗口操作符（1d / 7d / 30d…）。传 1d 时
        命中通常很少，这是预期行为——调用方据此判断要不要放宽窗口。
        """
        import urllib.parse

        results: List[Dict[str, Any]] = []
        if self._google_banned:
            return results

        encoded_q = urllib.parse.quote(keyword)

        # 尝试中英文两种区域配置
        region_configs = [
            ("zh-CN", "CN", "CN:zh-Hans"),
            ("en-US", "US", "US:en"),
        ]

        for hl, gl, ceid in region_configs:
            if len(results) >= max_results:
                break
            if deadline is not None and time.monotonic() >= deadline:
                logger.warning("⏱ 采集预算耗尽，Google News RSS 停止后续区域尝试")
                break

            for attempt in range(1, 4):
                if deadline is not None and time.monotonic() >= deadline:
                    logger.warning("⏱ 采集预算耗尽，Google News RSS 停止重试")
                    break
                try:
                    rss_url = (
                        f"https://news.google.com/rss/search"
                        f"?q={encoded_q}+when:{when}&hl={hl}&gl={gl}&ceid={ceid}"
                    )
                    logger.info("Google News RSS 搜索: {} (hl={}) (尝试 {})", keyword, hl, attempt)
                    # host 目前是源码里的字面量，插值只进查询串，本没有注入面。
                    # 仍然校验一次：把"host 不可变"从一条口头约定变成每次请求都
                    # 被执行的不变量，将来若有人把域名改成可配置项，这道闸已经在。
                    validate_public_url(rss_url, allow_private=False)
                    resp = self.session.get(rss_url, timeout=self.search_timeout, allow_redirects=False)
                    if resp.status_code != 200:
                        logger.warning("Google News RSS 返回 {}: {}", resp.status_code, hl)
                        if resp.status_code in (403, 429, 503):
                            self._google_banned = True
                            return results
                        if attempt < 3:
                            time.sleep(1.5 ** attempt)
                        continue
    
                    root = parse_rss(resp.text)
                    for item_elem in root.iter("item"):
                        title = ""
                        link = ""
                        pub_date = ""
                        source = ""
                        source_url = ""
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
                                # <source url="https://finance.sina.com.cn">新浪财经</source>
                                # item 的 <link> 只是 news.google.com 的跳转壳，真正的
                                # 发布方域名在 source 的 url 属性里。只取 text 会把整批
                                # 结果全记成 news.google.com：信源分级退化成"全是门户
                                # 转载"，集中度恒为单一来源，前端"原文"也全指向 Google。
                                source_url = (child.attrib.get("url") or "").strip()
                            elif tag == "description":
                                description = (child.text or "").strip()

                        if not title:
                            continue

                        # title 格式: "新闻标题 - 来源名"
                        if " - " in title and not source:
                            parts = title.rsplit(" - ", 1)
                            title, source = parts[0].strip(), parts[1].strip()
                        elif source and title.endswith(" - " + source):
                            # 已有 <source> 时标题仍带着 " - 来源" 后缀，前端会把来源
                            # 再显示一遍。只在后缀与已知来源完全一致时才剥，
                            # 标题本身含 " - " 的（"A - B 事件复盘"）不会被误伤。
                            title = title[: -(len(source) + 3)].strip()

                        # 真实发布方链接优先：RSS 的 source url > description 里的
                        # 原文链接 > Google 跳转壳。前两者都拿不到时才留壳，
                        # 那种情况下信源分级会明确落到"待核验"而不是猜一个层级。
                        orig_link = source_url or link
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
    def _search_generic(self, keyword: str, remaining: int,
                        deadline: Optional[float] = None) -> List[Dict[str, Any]]:
        """Bing News 网页抓取回退方案，多选择器兼容。"""
        if remaining <= 0 or self._bing_banned:
            return []

        logger.info("尝试通过 Bing News HTML 抓取补充搜索结果...")
        url = "https://www.bing.com/news/search"
        # 不能带 mkt=zh-CN：Bing 会 302 重定向到首页，返回的页面没有任何新闻卡片。
        params = {"q": keyword, "count": str(min(remaining, 30))}
        items: List[Dict[str, Any]] = []

        for attempt in range(1, 4):
            if deadline is not None and time.monotonic() >= deadline:
                logger.warning("⏱ 采集预算耗尽，Bing 抓取停止重试")
                break
            try:
                resp = self.session.get(url, params=params, timeout=self.search_timeout)
                if resp.status_code != 200:
                    logger.warning("Bing News 返回 {}: {}", resp.status_code, attempt)
                    if resp.status_code in (403, 429, 503):
                        self._bing_banned = True
                        return items
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
                    cards = [
                        a for a in all_links
                        if ("/news/" in a.get("href", "") or "/articles/" in a.get("href", ""))
                        and not _is_bing_ui_link(a.get("href", ""), a.get_text(strip=True))
                    ]
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
                    if _is_bing_ui_link(link, title):
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

                    # 来源提取：优先用卡片自带的 data-author（干净）。
                    # 不能直接取 div.source 的全文——它把相对时间（如“1y”）
                    # 和来源名拼在一起，会污染下游的来源分布统计。
                    source = (element.get("data-author") or "").strip()
                    if not source:
                        src_elem = (
                            element.select_one("div.source a")
                            or element.select_one("span.source a")
                            or element.select_one(".source a")
                        )
                        if src_elem:
                            source = src_elem.get_text(strip=True)
                    if not source:
                        source = "Bing News"

                    # 时间提取：Bing 把绝对日期放在 aria-label（如 8/29/2025），
                    # 卡片可见文本只是相对时间（如“1y”），解析不出来。
                    publish_time = ""
                    abs_elem = element.select_one("div.source span[aria-label]")
                    if abs_elem and abs_elem.get("aria-label"):
                        publish_time = abs_elem["aria-label"]
                    if not publish_time:
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
        """为搜索结果补充正文和摘要信息。

        抓正文是有成本的（每条一次 HTTP + 解析），只给最值得抓的那几条抓：
        先按信源层级排（权威信源优先），同层级内保持既有的时间倒序。
        之前是"取前 12 条"，那 12 条完全由搜索相关性决定，经常一排自媒体
        聚合稿，抓回来的正文对分析没有增量。
        """
        if not news_items:
            return

        tasks = [item for item in news_items if item.get("link")]
        if not tasks:
            return

        # 稳定排序：主键信源层级，保持时间倒序作为次序（sorted 是稳定的）
        tasks.sort(key=lambda item: item.get("source_tier", 4))

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

    def _safe_get(self, url: str, timeout: int = 15, max_hops: int = 3):
        """带 SSRF 防护的 GET：每一跳都重新校验，不允许跟着 302 溜进内网。

        requests 默认自动跟随重定向，一个公网 URL 302 到
        http://169.254.169.254/ 就绕过了入口校验，所以这里关掉自动跟随，
        自己按跳校验。超过 max_hops 或校验失败直接抛 ValueError。
        """
        current = url
        for _hop in range(max_hops + 1):
            # allow_private=False 是显式写死的：这里的 URL 来自搜索引擎
            # 返回内容，是不可信输入，绝不能被 MP_ALLOW_PRIVATE_LLM_ENDPOINTS
            # 一起放开。那个开关只该作用于"自己配的" LLM 端点。
            validate_public_url(current, allow_private=False)
            resp = self.session.get(
                current, timeout=timeout, allow_redirects=False)
            if resp.is_redirect or resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("Location", "")
                if not location:
                    return resp
                # 相对地址要按当前 URL 拼成绝对地址，否则校验的是个空壳
                current = requests.compat.urljoin(current, location)
                continue
            return resp
        raise ValueError(f"重定向次数超过 {max_hops} 跳，已放弃")

    def _extract_article_text(self, url: str) -> Tuple[str, str]:
        """从文章页面中提取正文与摘要。"""
        # URL 来自搜索引擎的返回内容，是不可信输入：必须先做协议/主机校验，
        # 否则一个指向 127.0.0.1 或 169.254.169.254 的"新闻链接"就能把后端
        # 变成探测内网的跳板。
        try:
            resp = self._safe_get(url)
        except ValueError as exc:
            logger.debug("跳过不安全的文章链接 {}: {}", url, exc)
            return "", ""
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
            "%Y/%m/%d",
            "%Y.%m.%d %H:%M",
            "%Y.%m.%d",
            "%m/%d/%Y",
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

        # RFC 822：Google News RSS 的 <pubDate> 就是这种格式
        # （"Tue, 22 Sep 2026 07:32:00 GMT"）。漏掉它会让每条 RSS 结果都
        # 退回 datetime.now()，整批样本的发布日全变成"今天"——按天序列只剩
        # 一个点、趋势预测不可行、证据时间线退化成一天，而界面只会显示
        # "本次运行未取得"，看不出是时间没解析出来。
        try:
            dt = parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError):
            dt = None
        if dt is not None:
            return dt.replace(tzinfo=None) if dt.tzinfo else dt

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

    # 近重复标题判定用的停用字符：同一件事五家媒体各发一篇，标题往往只差
    # 来源后缀、标点和空格（"宁德时代回应裁员传闻_网易财经" vs
    # "宁德时代回应裁员传闻"）。去掉这些再比，重复就浮出来了。
    _TITLE_NOISE = re.compile(
        r"[\s\-_—－|｜·,，。.!！?？:：;；\"'“”‘’()（）\[\]【】<>《》]+"
    )

    # 常见来源品牌名。标点已经被 _TITLE_NOISE 抹掉，品牌名会和正文粘在
    # 一起（"…传闻网易财经"），所以按结尾反复剥离，而不是按分隔符切。
    _SOURCE_BRANDS = (
        "新华网", "新华社", "人民网", "央视网", "央视新闻", "中国新闻网",
        "中新网", "澎湃新闻", "界面新闻", "第一财经", "财新网", "财联社",
        "每日经济新闻", "经济观察报", "21世纪经济报道", "证券时报",
        "上海证券报", "中国证券报", "新浪财经", "网易财经", "腾讯新闻",
        "腾讯网", "搜狐网", "搜狐财经", "凤凰网", "百度", "百家号",
        "知乎", "微博", "抖音", "今日头条", "一点资讯", "东方财富",
        "金融界", "和讯网", "雪球", "观察者网", "环球网", "参考消息",
    )

    @classmethod
    def _title_signature(cls, title: str) -> str:
        """把标题归一成一个可比较的签名。

        只做字符级归一（去标点/空白/来源品牌后缀），不做语义相似度：
        编辑距离之类的阈值没有客观依据，同一个词换个说法就判不出重复，
        还会把两条不同事件误并成一条。签名相同才合并，宁少不多。
        """
        if not title:
            return ""
        sig = cls._TITLE_NOISE.sub("", str(title).lower())
        changed = True
        while changed:
            changed = False
            for brand in cls._SOURCE_BRANDS:
                b = brand.lower()
                if sig.endswith(b) and len(sig) > len(b):
                    sig = sig[: -len(b)]
                    changed = True
                    break
        return sig

    def _deduplicate_near_duplicates(
        self, news_list: List[Dict[str, Any]], min_len: int = 8
    ) -> List[Dict[str, Any]]:
        """按标题签名合并同一事件的重复报道。

        链接去重解决不了"同一稿件被多家转载"：URL 各不相同，于是同一条
        传闻在情绪统计里被计了五次，负面占比直接虚高。这里保留最早出现的
        一条（调用方已按发布时间降序排过，所以是保留最新的一条）。
        """
        seen: Dict[str, Dict[str, Any]] = {}
        dropped = 0
        for news in news_list:
            title = news.get("title") or ""
            sig = self._title_signature(title)
            # 标题太短的不做签名去重："宁德时代"四个字和任何含它的标题
            # 都可能撞车，误并的代价比漏并大。
            if len(sig) < min_len:
                key = f"raw::{news.get('link') or title}"
            else:
                key = f"sig::{sig}"
            if key in seen:
                dropped += 1
                continue
            seen[key] = news
        if dropped:
            logger.info("🧹 标题近重复合并：丢弃 {} 条转载稿", dropped)
        return list(seen.values())

    @staticmethod
    def _annotate_sources(news_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """给每条数据打上信源层级，供证据流分组与统计说明使用。"""
        try:
            from .source_registry import annotate as _annotate
            return _annotate(news_list)
        except Exception as exc:  # noqa: BLE001
            logger.debug("信源分级失败（不影响主流程）: {}", exc)
            return news_list


__all__ = ["CustomSearchCollector"]
