"""信源可信度分级的测试。

分级是情绪占比解释力的前提：把一条自媒体推文和一条央媒快讯算成同一个
样本，正面率/负面率就被稀释得没有意义。这里锁定三件事：
  1. 按域名后缀判定，子域名归到同一层；
  2. 未命中的域名不冒充实名（有 URL 归 T3，无 URL 归 T4）；
  3. annotate / tier_distribution 给每条数据补的字段齐全且不丢原数据。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.collect.source_registry import (
    TIERS,
    _DOMAIN_TIERS,
    _normalize_domain,
    annotate,
    tier_distribution,
    tier_for_source,
    tier_label,
)


def test_authority_domains_map_to_tier_1():
    for url in (
        "https://www.xinhuanet.com/2026-09/22/c_1.htm",
        "http://news.cn/politics/2026-09/22/c_1.htm",
        "https://www.gov.cn/zhengce/2026-09/22/content_1.htm",
        "https://finance.people.com.cn/n1/2026/0922/c1.htm",
    ):
        assert tier_for_source("", url) == 1, url


def test_subdomains_inherit_the_suffix_tier():
    # 写后缀而不是完整域名的意义就在这里：news.xxx.com 自动跟着 xxx.com
    assert tier_for_source("", "https://news.xinhuanet.com/a") == 1
    # 门户的财经子频道跟着门户走，归 T3：它没有独立采编，
    # 与 T2"主流财经与行业媒体"不是一回事。
    assert tier_for_source("", "https://finance.sina.com.cn/chanjing/a.html") == 3


def test_professional_media_map_to_tier_2():
    for url in (
        "https://www.caixin.com/2026-09-22/1.html",
        "https://www.yicai.com/news/1.html",
        "https://www.reuters.com/markets/1",
    ):
        assert tier_for_source("", url) == 2, url


def test_portals_and_aggregators_map_to_tier_3():
    for url in (
        "https://www.toutiao.com/article/1/",
        "https://baijiahao.baidu.com/s?id=1",
        "https://zhuanlan.zhihu.com/p/1",
    ):
        assert tier_for_source("", url) == 3, url


def test_unknown_domain_with_url_is_tier_3_not_tier_4():
    # 有域名但表里没有：不冒充实名，但也不该直接判死刑
    assert tier_for_source("某不知名站点", "https://some-random-site.example/news/1") == 3


def test_missing_url_is_tier_4():
    # 本地数据 / 搜索引擎只给了来源名，没有任何可核验的域名
    assert tier_for_source("本地数据", "") == 4
    assert tier_for_source("某自媒体", None) == 4


def test_source_name_alone_never_promotes_a_tier():
    # 来源名字段是搜索引擎给的，写法五花八门（"新华网" / "新华社新闻" /
    # "Xinhua"），拿名字做关键词匹配必然漏判——必须只认域名。
    assert tier_for_source("新华网", "") == 4
    assert tier_for_source("Xinhua News Agency", "") == 4


def test_labels_come_from_the_tier_table():
    assert tier_label(1) == "权威信源"
    assert tier_label(2) == "专业媒体"
    assert tier_label(3) == "门户转载"
    assert tier_label(4) == "待核验"
    # 越界值不能 KeyError
    assert tier_label(99) == "待核验"


def test_annotate_adds_fields_without_dropping_originals():
    items = [
        {"title": "A", "link": "https://www.xinhuanet.com/a", "source": "新华网"},
        {"title": "B", "url": "https://zhuanlan.zhihu.com/p/1", "source": "知乎专栏"},
        {"title": "C", "source": "本地数据"},
    ]
    out = annotate(items)

    assert len(out) == 3
    # 原始字段必须原样保留，annotate 是增强不是替换
    assert out[0]["title"] == "A" and out[0]["source"] == "新华网"
    assert out[0]["source_tier"] == 1
    assert out[0]["source_tier_label"] == "权威信源"
    assert out[0]["source_domain"] == "www.xinhuanet.com"

    assert out[1]["source_tier"] == 3
    assert out[1]["source_domain"] == "zhuanlan.zhihu.com"

    # 无 URL 的本地数据：域名空串，层级 T4，不做任何猜测
    assert out[2]["source_tier"] == 4
    assert out[2]["source_domain"] == ""


def test_tier_distribution_counts_every_tier_key():
    items = annotate([
        {"title": "A", "url": "https://www.xinhuanet.com/a"},
        {"title": "B", "url": "https://www.xinhuanet.com/b"},
        {"title": "C", "url": "https://www.caixin.com/c"},
        {"title": "D", "source": "本地数据"},
    ])
    dist = tier_distribution(items)

    # 四个层级的键必须都在，缺键会让前端的分段统计渲染出 undefined
    assert set(dist.keys()) == {"1", "2", "3", "4"}
    assert dist == {"1": 2, "2": 1, "3": 0, "4": 1}


def test_tier_distribution_annotates_unannotated_items():
    # 没走 annotate 的原始列表也要能统计（collect_meta 可能在别处生成）
    dist = tier_distribution([{"title": "A", "url": "https://www.ce.cn/a"}])
    assert dist["1"] == 1


def test_tier_table_is_ordered_and_documented():
    # 层级表是给用户看的口径说明，四层必须齐全且各自有 desc
    assert sorted(TIERS) == [1, 2, 3, 4]
    for tier, meta in TIERS.items():
        assert meta["label"] and meta["short"] and meta["desc"], tier


def test_domain_tiers_are_disjoint():
    # 同一个后缀不能出现在两层里。sina/sohu/163/qq/ifeng 曾经同时挂在 T2 和
    # T3 上，实际层级取决于 dict 遍历顺序——统计口径会随代码改动漂移，
    # 而这种漂移在界面上完全看不出来。
    seen = {}
    for tier, suffixes in _DOMAIN_TIERS.items():
        for suffix in suffixes:
            assert suffix not in seen, f"{suffix} 同时出现在 T{seen[suffix]} 和 T{tier}"
            seen[suffix] = tier


def test_portal_domains_and_their_finance_channels_are_tier_3():
    for url in ("https://finance.sina.com.cn/a",
                "https://www.sohu.com/a",
                "https://news.qq.com/a",
                "https://www.163.com/a",
                "https://finance.ifeng.com/a"):
        assert tier_for_source("", url) == 3, url


def test_independent_financial_media_stay_in_tier_2():
    for url in ("https://www.caixin.com/a",
                "https://www.thepaper.cn/a",
                "https://www.eastmoney.com/a",
                "https://wallstreetcn.com/a"):
        assert tier_for_source("", url) == 2, url


def test_google_news_redirect_shell_is_not_a_publisher_domain():
    # Google News 的跳转壳不是发布方。采集器必须从 RSS 的 <source url>
    # 属性拿真实域名；若退回只读 item link，整批结果的 source_domain 都会变成
    # news.google.com——信源集中度恒等于 1（"只有一个来源"），分级全落 T3，
    # 前端"原文"也全指向 Google。这条测试锁住跳转壳不被当作发布方。
    shell = "https://news.google.com/rss/articles/CBMidkFVX3lxTE9FeEdHVEtVN2"
    host = _normalize_domain(shell)
    assert host == "news.google.com"
    assert all(host != s for suffixes in _DOMAIN_TIERS.values() for s in suffixes)
