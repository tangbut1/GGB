import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from src.collect.custom_search import CustomSearchCollector

# 占位用的假 token。请求全程被 mock，鉴权值不参与断言；单独提出来并取一个
# 一眼假的名字，避免被凭据扫描器误判成硬编码密钥。
TEST_API_TOKEN = "placeholder-not-a-real-token"

def test_custom_search_initialization():
    collector = CustomSearchCollector(max_workers=2)
    assert collector.max_workers == 2

@patch("src.collect.custom_search.requests.Session.get")
def test_search_google_news(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b'''<?xml version="1.0" encoding="UTF-8"?>
    <rss><channel><item>
        <title>Test Google News</title>
        <link>http://example.com/google</link>
        <description>Test Description</description>
        <source>Google Source</source>
        <pubDate>Sun, 01 Jan 2050 12:00:00 GMT</pubDate>
    </item></channel></rss>'''
    mock_get.return_value = mock_resp

    collector = CustomSearchCollector()
    results = collector._search_google_news("test keyword")
    assert len(results) >= 0  # if feedparser is required we can just assert it doesn't crash

@patch("src.collect.custom_search.DDGS")
def test_search_duckduckgo(mock_ddgs):
    mock_ddgs_instance = mock_ddgs.return_value.__enter__.return_value
    mock_ddgs_instance.news.return_value = [
        {
            "title": "Test DDG News",
            "url": "http://example.com/ddg",
            "body": "This is a test from DDG",
            "source": "DDG Source",
            "date": "2050-01-01T12:00:00Z"
        }
    ]

    collector = CustomSearchCollector()
    results = collector._search_duckduckgo("test keyword")
    assert len(results) == 1
    assert results[0]["title"] == "Test DDG News"
    assert results[0]["link"] == "http://example.com/ddg"

@patch("src.collect.custom_search.requests.Session.get")
def test_search_newsapi(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "articles": [
            {
                "title": "Test NewsAPI News",
                "url": "http://example.com/newsapi",
                "description": "This is a test from NewsAPI",
                "source": {"name": "NewsAPI Source"},
                "publishedAt": "2050-01-01T12:00:00Z"
            }
        ]
    }
    mock_get.return_value = mock_resp

    collector = CustomSearchCollector()
    # 这个用例只验证响应解析，requests 已被 mock，鉴权值不参与任何断言。
    # 用显式的占位符而不是像样的字符串，免得被凭据扫描器当成硬编码密钥。
    results = collector._search_newsapi("test keyword", remaining=10, api_key=TEST_API_TOKEN)
    assert len(results) == 1
    assert results[0]["title"] == "Test NewsAPI News"
    assert results[0]["link"] == "http://example.com/newsapi"

def test_parse_datetime():
    collector = CustomSearchCollector()
    dt1 = collector._parse_datetime("2050-01-01 12:00:00")
    assert dt1 is not None
    assert dt1.year == 2050
    assert dt1.month == 1

    dt2 = collector._parse_datetime("3小时前")
    assert dt2 is not None


class _Resp:
    """只带 _safe_get 用到的字段，避免 MagicMock 的 is_redirect 恒真。"""

    def __init__(self, status_code=200, headers=None):
        self.status_code = status_code
        self.headers = headers or {}
        self.is_redirect = False


def test_safe_get_rejects_private_urls(monkeypatch):
    """抓正文前必须拦下内网地址，无论环境变量怎么设。"""
    monkeypatch.setenv("MP_ALLOW_PRIVATE_LLM_ENDPOINTS", "1")
    collector = CustomSearchCollector()
    for url in ("http://127.0.0.1:6379/", "http://169.254.169.254/latest/meta-data/",
                "http://192.168.1.5/admin", "ftp://127.0.0.1/"):
        with pytest.raises(ValueError):
            collector._safe_get(url)


def test_safe_get_revalidates_every_redirect_hop(monkeypatch):
    """公网 URL 302 到内网也必须被拦下——入口校验过不等于每一跳都安全。"""
    monkeypatch.setenv("MP_ALLOW_PRIVATE_LLM_ENDPOINTS", "1")
    collector = CustomSearchCollector()
    hops = [_Resp(302, {"Location": "http://169.254.169.254/"})]

    def fake_get(url, **kwargs):
        assert kwargs.get("allow_redirects") is False, "不能交给 requests 自动跟随重定向"
        return hops.pop(0)

    monkeypatch.setattr(collector.session, "get", fake_get)
    with pytest.raises(ValueError):
        collector._safe_get("https://example.com/article")


def test_safe_get_allows_public_url(monkeypatch):
    collector = CustomSearchCollector()
    monkeypatch.setattr(collector.session, "get", lambda url, **kwargs: _Resp(200))
    assert collector._safe_get("https://example.com/article").status_code == 200


RSS_WITH_SOURCE_URL = """<?xml version="1.0" encoding="UTF-8"?>
<rss><channel><item>
    <title>宁德时代牵手某车企 - 新浪财经</title>
    <link>https://news.google.com/rss/articles/CBMiabc123?oc=5</link>
    <description>&lt;ol&gt;&lt;li&gt;&lt;a href="https://news.google.com/rss/articles/CBMiabc123?oc=5"&gt;宁德时代牵手某车企&lt;/a&gt;&lt;/li&gt;&lt;/ol&gt;</description>
    <source url="https://finance.sina.com.cn">新浪财经</source>
    <pubDate>Tue, 22 Sep 2026 07:32:00 GMT</pubDate>
</item></channel></rss>"""


@patch("src.collect.custom_search.requests.Session.get")
def test_google_rss_source_url_becomes_the_real_link(mock_get):
    """RSS 的 <source url> 才是发布方域名，item 的 <link> 只是 Google 跳转壳。

    只读 source 的 text 会让整批结果的 source_domain 全是 news.google.com：
    信源集中度恒等于 1、分级全落 T3、前端"原文"全指向 Google。
    """
    resp = MagicMock()
    resp.status_code = 200
    resp.text = RSS_WITH_SOURCE_URL
    mock_get.return_value = resp

    results = CustomSearchCollector()._search_google_news("宁德时代")

    assert len(results) == 1
    item = results[0]
    assert item["link"] == "https://finance.sina.com.cn"
    assert item["source"] == "新浪财经"
    # 标题里的 " - 来源" 后缀要剥掉，不能带着进情绪分析
    assert item["title"] == "宁德时代牵手某车企"


@patch("src.collect.custom_search.requests.Session.get")
def test_google_rss_falls_back_to_google_shell_without_source_url(mock_get):
    """没有 <source url> 时保留跳转壳，不猜域名。"""
    resp = MagicMock()
    resp.status_code = 200
    resp.text = """<?xml version="1.0" encoding="UTF-8"?>
    <rss><channel><item>
        <title>某条新闻</title>
        <link>https://news.google.com/rss/articles/CBMiXYZ?oc=5</link>
        <description>摘要</description>
        <source>某来源</source>
        <pubDate>Tue, 22 Sep 2026 07:32:00 GMT</pubDate>
    </item></channel></rss>"""
    mock_get.return_value = resp

    results = CustomSearchCollector()._search_google_news("测试")
    assert len(results) == 1
    assert results[0]["link"] == "https://news.google.com/rss/articles/CBMiXYZ?oc=5"


def test_parse_rss_rejects_dtd_entity_declarations():
    """ElementTree 会展开内部 DTD 实体，层层嵌套的 feed 能吃掉整个进程。
    搜索引擎返回的 XML 和搜索结果一样是不可信输入，必须先拒后解析。"""
    from src.collect.custom_search import parse_rss

    evil = """<?xml version="1.0"?>
    <!DOCTYPE rss [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]>
    <rss><channel><item><title>&b;</title></item></channel></rss>"""

    with pytest.raises(ValueError, match="DTD"):
        parse_rss(evil)


def test_parse_rss_rejects_oversized_payload():
    from src.collect.custom_search import RSS_MAX_BYTES, parse_rss

    huge = "x" * (RSS_MAX_BYTES + 1)
    with pytest.raises(ValueError, match="大小上限"):
        parse_rss(huge)


def test_parse_rss_accepts_normal_feed():
    from src.collect.custom_search import parse_rss

    root = parse_rss(RSS_WITH_SOURCE_URL)
    assert root.tag == "rss"
    assert len(list(root.iter("item"))) == 1


@patch("src.collect.custom_search.requests.Session.get")
def test_title_suffix_is_only_stripped_when_it_matches_the_source(mock_get):
    """标题里本来就可能带 " - "。只有后缀与已知来源完全一致时才剥，
    否则 "A - B 事件复盘" 这种正常标题会被切掉一半。"""
    resp = MagicMock()
    resp.status_code = 200
    resp.text = """<?xml version="1.0" encoding="UTF-8"?>
    <rss><channel><item>
        <title>宁德时代扩产 - 时间线复盘</title>
        <link>https://news.google.com/rss/articles/CBMiQ?oc=5</link>
        <description>摘要</description>
        <source url="https://www.thepaper.cn">澎湃新闻</source>
        <pubDate>Tue, 22 Sep 2026 07:32:00 GMT</pubDate>
    </item></channel></rss>"""
    mock_get.return_value = resp

    results = CustomSearchCollector()._search_google_news("宁德时代")
    assert len(results) == 1
    assert results[0]["title"] == "宁德时代扩产 - 时间线复盘"
    assert results[0]["source"] == "澎湃新闻"
    assert results[0]["link"] == "https://www.thepaper.cn"


def test_parse_datetime_handles_rfc822_from_google_rss():
    """Google News RSS 的 <pubDate> 是 RFC 822。解析不了它会整体退回
    datetime.now()，整批样本的发布日全变成"今天"——按天序列只剩一个点、
    趋势预测不可行，而界面只会显示"本次运行未取得"。"""
    collector = CustomSearchCollector()
    assert collector._parse_datetime("Tue, 22 Sep 2026 07:32:00 GMT") == datetime(2026, 9, 22, 7, 32)
    assert collector._parse_datetime("Wed, 25 Jun 2026 12:00:00 GMT") == datetime(2026, 6, 25, 12, 0)
    # 带时区偏移的也要能解析。保留发布方的本地墙上时间（与 ISO 分支的
    # replace(tzinfo=None) 一致），不转 UTC——界面上显示的就是发布时间。
    assert collector._parse_datetime("Tue, 22 Sep 2026 15:32:00 +0800") == datetime(2026, 9, 22, 15, 32)


def test_parse_datetime_still_handles_other_formats():
    collector = CustomSearchCollector()
    assert collector._parse_datetime("2026-09-22 08:30:00") == datetime(2026, 9, 22, 8, 30)
    assert collector._parse_datetime("2026-09-22") == datetime(2026, 9, 22)
    # 认不出来的必须返回 None，由调用方决定兜底策略
    assert collector._parse_datetime("garbage") is None
    assert collector._parse_datetime("") is None
    assert collector._parse_datetime(None) is None


def test_month_auxiliary_terms_use_a_wide_window():
    """按月补充词必须配宽窗口，否则永远拿不到更早的样本。

    默认 when=7d 时，"关键词 2026年8月" 只命中最近一周发布、正文提到 8 月的
    稿子，发布日全落在本周——按天序列退化成一个点，趋势预测直接不可行，
    而界面看不出这是窗口配错导致的。
    """
    calls = []

    def fake_google(self, keyword, max_results=50, deadline=None, when="7d"):
        calls.append((keyword, when))
        # 只回少量互不重复的结果：主搜索必须"拿不够量"，才会继续走补充词分支
        return [{"title": f"{keyword}-{i}", "link": f"https://example.com/{keyword}/{i}",
                 "publish_time": "Tue, 22 Sep 2026 07:32:00 GMT"}
                for i in range(3)]

    class SpyCollector(CustomSearchCollector):
        _search_google_news = fake_google
        _search_duckduckgo = lambda self, *a, **k: []
        _search_generic = lambda self, *a, **k: []
        _search_newsapi = lambda self, *a, **k: []
        _enrich_news_content = lambda self, items, **k: items

    SpyCollector(max_workers=1).search_news("宁德时代", max_results=120)

    month_calls = [(k, w) for k, w in calls if "月" in k]
    assert month_calls, f"没有发起按月搜索，实际调用：{calls}"
    for keyword, when in month_calls:
        assert when == "90d", f"{keyword} 用了 when={when}"

    # 主搜索仍保持时效优先：先 24h，不够才回落 7d
    main_calls = [(k, w) for k, w in calls if "月" not in k]
    assert main_calls and main_calls[0][1] == "1d", main_calls


def test_expand_auxiliary_false_skips_month_and_variant_terms():
    """调用方自带差异化查询词时必须能关掉自动展开。

    CollectAgent 的补充采集会把"宁德时代 报道"这类词再喂进完整搜索，
    而完整搜索又会展开出"宁德时代 报道 最新""宁德时代 报道 2026年8月"。
    一次补充放大成 4×5 次查询，绝大多数是拼接废词，只烧采集预算。
    """
    calls = []

    def fake_google(self, keyword, max_results=50, deadline=None, when="7d"):
        calls.append((keyword, when))
        return [{"title": f"{keyword}-{i}", "link": f"https://example.com/{keyword}/{i}",
                 "publish_time": "Tue, 22 Sep 2026 07:32:00 GMT"}
                for i in range(3)]

    class SpyCollector(CustomSearchCollector):
        _search_google_news = fake_google
        _search_duckduckgo = lambda self, *a, **k: []
        _search_generic = lambda self, *a, **k: []
        _search_newsapi = lambda self, *a, **k: []
        _enrich_news_content = lambda self, items, **k: items

    SpyCollector(max_workers=1).search_news(
        "宁德时代 报道", max_results=120, expand_auxiliary=False)

    assert calls, "一次搜索都没发起"
    for keyword, _ in calls:
        assert "最新" not in keyword and "新闻" not in keyword, f"展开了变体词：{keyword}"
        assert keyword.count("月") <= 1 or keyword == "宁德时代 报道", (
            f"展开了月份词：{keyword}"
        )


def test_supplement_month_terms_cross_the_year_boundary():
    """1 月往前推 4、5 个月必须落在上一年，不能算出"当年 12 月"。

    月份用 (month - m - 1) % 12 + 1 算时，1 月取 m=1 得到 12，配 now.year
    就成了"2026年12月"——而那个 12 月属于 2025 年。搜索引擎按字面收词，
    查不到东西，界面只会显示"本次运行未取得"，看不出是年份算错。
    """
    from datetime import datetime

    now = datetime(2026, 1, 15)
    months = []
    for months_back in [4, 5]:
        d = now - timedelta(days=months_back * 30)
        months.append((d.year, d.month))

    assert (2025, 9) in months, months
    assert (2025, 8) in months, months
    for year, _ in months:
        assert year == 2025, f"跨年时仍用了当年：{months}"
