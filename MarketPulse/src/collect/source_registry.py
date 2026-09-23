"""信源可信度分级。

情绪分布的统计意义完全取决于样本是谁说的。把一条自媒体推文和一条新华社
快讯算成同一个"样本"，正面/负面比例就被稀释得没有解释力——所以每条数据
都要带一个可信度层级，右侧"证据"Tab 按层级分组展示，"热词"与"情感"的
分母也能分开统计。

分级依据是信源的编辑属性，不是内容质量：
  T1 权威通讯社 / 央媒 / 监管机构    —— 有一线采编权和事实核查流程
  T2 主流财经与行业媒体            —— 有编辑审核，可能有立场
  T3 门户 / 地方媒体 / 聚合站      —— 转载为主，事实层薄
  T4 自媒体 / 论坛 / 未知来源      —— 无法核验，只作情绪信号

匹配按域名后缀做，不按关键词：来源名字段是搜索引擎给的，写法五花八门
（"新华网"、"新华社新闻"、"Xinhua"），域名只有一个。未命中的一律 T4，
不猜。
"""

from __future__ import annotations

from typing import Dict, Iterable, List
from urllib.parse import urlparse

# 层级定义：数字越小越权威。label 直接展示给用户。
TIERS: Dict[int, Dict[str, str]] = {
    1: {"key": "authority", "label": "权威信源", "short": "T1",
        "desc": "通讯社 / 央媒 / 监管机构，有一线采编与事实核查流程"},
    2: {"key": "professional", "label": "专业媒体", "short": "T2",
        "desc": "主流财经与行业媒体，有编辑审核，可能带立场"},
    3: {"key": "portal", "label": "门户转载", "short": "T3",
        "desc": "门户 / 地方媒体 / 聚合站，以转载为主"},
    4: {"key": "unverified", "label": "待核验", "short": "T4",
        "desc": "自媒体 / 论坛 / 未识别来源，仅作情绪信号，不作为事实依据"},
}

# 域名后缀 → 层级。写后缀而不是完整域名，子域名（news.xinhuanet.com、
# finance.qq.com）自动归到同一层。
#
# 两张表必须互不相交。sina/sohu/163/qq/ifeng 既是门户也是财经渠道的宿主，
# 曾经同时出现在 T2 和 T3 里，实际层级取决于 dict 的遍历顺序——同一个域名
# 在不同版本下会落到不同层，统计口径跟着漂移。门户按定义归 T3（转载为主、
# 事实层薄），它们的财经子频道一并归 T3；T2 只留有独立采编的财经与行业媒体。
_DOMAIN_TIERS: Dict[int, tuple] = {
    1: (
        "xinhuanet.com", "news.cn", "gov.cn", "people.com.cn",
        "cctv.com", "cntv.cn", "chinadaily.com.cn", "cnr.cn",
        "ce.cn", "stdaily.com", "81.cn",
    ),
    2: (
        "caixin.com", "yicai.com", "21jingji.com", "eeo.com.cn",
        "nbd.com.cn", "stcn.com", "cnstock.com", "cs.com.cn",
        "hexun.com", "jrj.com.cn", "wallstreetcn.com", "gelonghui.com",
        "cls.cn", "10jqka.com.cn", "eastmoney.com", "thepaper.cn",
        "jfdaily.com", "bjnews.com.cn", "cfi.cn", "pingwest.com",
        "36kr.com", "iyiou.com", "huxiu.com", "tmtpost.com",
        "reuters.com", "bloomberg.com", "ft.com", "wsj.com",
        "nikkei.com", "economist.com",
    ),
    3: (
        "qq.com", "163.com", "sohu.com", "sina.com.cn", "ifeng.com",
        "toutiao.com", "baijiahao.baidu.com", "zhihu.com", "douban.com",
        "tianya.cn", "m.sm.cn", "quanmin.baidu.com",
    ),
}


def _normalize_domain(url: str) -> str:
    if not url:
        return ""
    raw = url.strip().lower()
    if "//" not in raw:
        raw = "//" + raw
    try:
        from urllib.parse import urlparse as _up
        host = _up(raw).hostname or ""
    except ValueError:
        return ""
    return host.lstrip(".")


def tier_for_source(source: str = "", url: str = "") -> int:
    """返回信源层级（1-4）。域名优先，来源名只做空值兜底。"""
    host = _normalize_domain(url)
    if host:
        for tier, suffixes in _DOMAIN_TIERS.items():
            for suffix in suffixes:
                if host == suffix or host.endswith("." + suffix):
                    return tier
        # 有域名但不在表里：仍可能是正规站点，但不冒充实名，
        # 归 T3（"门户转载"）而不是 T4，等表补全。
        return 3
    # 没有 URL（本地数据 / 搜索引擎只给了来源名）：按未识别处理
    return 4


def tier_label(tier: int) -> str:
    return TIERS.get(tier, TIERS[4])["label"]


def annotate(items: Iterable[dict]) -> List[dict]:
    """给每条数据补上 source_tier / source_tier_label / source_domain。"""
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        url = item.get("link") or item.get("url") or ""
        tier = tier_for_source(item.get("source", ""), url)
        item = dict(item)
        item["source_tier"] = tier
        item["source_tier_label"] = tier_label(tier)
        item["source_domain"] = _normalize_domain(url)
        out.append(item)
    return out


def tier_distribution(items: Iterable[dict]) -> Dict[str, int]:
    """各层级条数统计，用于采集元信息与前端方法论说明。"""
    dist = {str(t): 0 for t in TIERS}
    for item in items:
        if not isinstance(item, dict):
            continue
        tier = item.get("source_tier")
        if tier is None:
            tier = tier_for_source(item.get("source", ""), item.get("link") or item.get("url") or "")
        dist[str(tier)] = dist.get(str(tier), 0) + 1
    return dist


__all__ = ["TIERS", "tier_for_source", "tier_label", "annotate", "tier_distribution"]
