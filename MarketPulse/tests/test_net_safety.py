"""SSRF 防护的测试。

服务端拿到一个 URL 就发请求时，这个 URL 可能来自用户的输入、搜索引擎
的结果、或者配置文件里的 base_url。任一条指向 localhost / 内网 / 环回 /
链路本地 / 保留地址，都会把"发请求"变成"探针"。这一组测试锁定判据本身。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from src.net_safety import (
    is_blocked_ip,
    validate_public_url,
    safe_output_path,
    safe_write_path,
)


# ── 协议白名单 ────────────────────────────────────────────────────────

@pytest.mark.parametrize("url", [
    "ftp://example.com/file",
    "file:///etc/passwd",
    "gopher://example.com/",
    "javascript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "//example.com/path",
    "example.com/path",
    "",
    "   ",
])
def test_non_http_schemes_are_rejected(url):
    with pytest.raises(ValueError):
        validate_public_url(url)


@pytest.mark.parametrize("url", [
    "http://example.com/a",
    "https://example.com/a",
    "https://example.com:8443/a?x=1#frag",
    "HTTPS://EXAMPLE.COM/A",
])
def test_plain_http_urls_are_accepted(url):
    assert validate_public_url(url) == url


# ── 内嵌凭据 ──────────────────────────────────────────────────────────

def test_embedded_credentials_are_rejected():
    # user:pass@host 会把凭据带进请求头，也可能用来混淆 host 解析
    with pytest.raises(ValueError):
        validate_public_url("https://user:pass@example.com/")


# ── 私网 / 环回 / 保留地址 ────────────────────────────────────────────

@pytest.mark.parametrize("ip", [
    "127.0.0.1", "127.8.9.10",          # 环回
    "0.0.0.0",                          # 未指定
    "10.1.2.3", "172.16.0.1", "172.31.255.255",  # 私网
    "192.168.1.5",                      # 私网
    "169.254.1.1",                      # 链路本地（云元数据常用）
    "100.64.0.1",                       # CGNAT
    "192.0.2.1", "198.51.100.7", "203.0.113.9",  # 文档保留段
    "224.0.0.1", "239.255.255.255",    # 组播
    "240.0.0.1", "255.255.255.255",    # 保留 / 广播
    "::1", "fe80::1", "fc00::1", "::",  # IPv6 环回 / 链路本地 / 唯一本地
])
def test_blocked_ips(ip):
    assert is_blocked_ip(ip), ip


@pytest.mark.parametrize("ip", [
    "8.8.8.8", "1.1.1.1", "93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946",
])
def test_public_ips_are_allowed(ip):
    assert not is_blocked_ip(ip), ip


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:6379/",
    "http://localhost/",
    "http://192.168.1.5/admin",
    "http://10.0.0.1/",
    "http://169.254.169.254/latest/meta-data/",
    "http://[::1]/",
])
def test_internal_targets_are_rejected(url):
    with pytest.raises(ValueError):
        validate_public_url(url)


# ── 环境变量逃生阀 ────────────────────────────────────────────────────

def test_private_endpoints_opt_in_via_env(monkeypatch):
    # 本地开发 / 自建 vLLM 需要打内网端点，用显式开关放行而不是改代码。
    # 默认必须是关的：安全性不能依赖"没人去设这个变量"。
    monkeypatch.delenv("MP_ALLOW_PRIVATE_LLM_ENDPOINTS", raising=False)
    with pytest.raises(ValueError):
        validate_public_url("http://127.0.0.1:8000/v1")

    monkeypatch.setenv("MP_ALLOW_PRIVATE_LLM_ENDPOINTS", "1")
    assert validate_public_url("http://127.0.0.1:8000/v1") == "http://127.0.0.1:8000/v1"


def test_env_opt_in_still_blocks_non_http(monkeypatch):
    # 逃生阀只解私网地址，不解协议白名单
    monkeypatch.setenv("MP_ALLOW_PRIVATE_LLM_ENDPOINTS", "1")
    with pytest.raises(ValueError):
        validate_public_url("ftp://127.0.0.1/")


def test_explicit_false_overrides_env_opt_in(monkeypatch):
    # allow_private=False 是硬写死，不受环境影响。采集器抓文章正文走这
    # 一条——URL 来自搜索引擎返回内容，是不可信输入，不能因为有人为了
    # 跑本地 vLLM 而设了开关就一起放开。
    monkeypatch.setenv("MP_ALLOW_PRIVATE_LLM_ENDPOINTS", "1")
    with pytest.raises(ValueError):
        validate_public_url("http://127.0.0.1:8000/v1", allow_private=False)
    with pytest.raises(ValueError):
        validate_public_url("http://169.254.169.254/", allow_private=False)


# ── 无法解析的域名 ────────────────────────────────────────────────────

def test_unresolvable_host_is_rejected_not_passed_through():
    # 解析失败时不能"放过去试试"——DNS  rebinding 的第一跳就是解析失败
    with pytest.raises(ValueError):
        validate_public_url("https://this-host-does-not-exist-zzzq.example/")


# ── 写入路径收敛 ──────────────────────────────────────────────────────

def test_safe_output_path_rejects_parent_refs_in_a_component(tmp_path):
    # 单个分量里带分隔符或上级引用，说明调用方把整条路径塞进了一个参数
    for bad in ["../escape", "a/b", "..", "/etc/passwd"]:
        with pytest.raises(ValueError):
            safe_output_path(tmp_path, bad)


def test_safe_output_path_joins_clean_components(tmp_path):
    target = safe_output_path(tmp_path, "raw", "news.json")
    assert target.parent == tmp_path / "raw"
    assert target.name == "news.json"


def test_safe_output_path_confines_result_to_base(tmp_path):
    # 拼完必须仍落在 base 内；用绝对路径顶掉前缀的那一招在这里过不去
    with pytest.raises(ValueError):
        safe_output_path(tmp_path, "..", "outside.json")
    assert safe_output_path(tmp_path, "sub").is_relative_to(tmp_path)


def test_safe_write_path_allows_configured_output_dirs():
    # 输出目录本身可以由 config 决定（results_dir 等），不该被拦
    for ok in ["data/processed/cleaned_news.json", "results/reports/x.html"]:
        assert safe_write_path(ok).name in ("cleaned_news.json", "x.html")


def test_safe_write_path_rejects_parent_refs():
    for bad in ["../etc/passwd", "a/../../b", "data/../../etc/x"]:
        with pytest.raises(ValueError):
            safe_write_path(bad)
