"""外发请求的目标地址安全校验。

采集器会去抓搜索结果里文章的正文，而那些 URL 来自第三方搜索引擎的
返回内容——等于把不可信输入直接喂给了 requests。一个指向
http://127.0.0.1:6379 或 http://169.254.169.254/ 的"新闻链接"就能让
后端变成探测内网的跳板（SSRF）。

这里只放与业务无关的通用判据：协议白名单、禁止内嵌凭证、DNS 解析结果
不得落在环回/私有/保留段。采集器和 LLM 端点校验共用同一套逻辑，
避免两处各写一份、后来只改了一处。
"""

from __future__ import annotations

import ipaddress
import os
import socket
from pathlib import Path
from urllib.parse import urlparse


def is_blocked_ip(ip_str: str) -> bool:
    """私有 / 环回 / 链路本地 / 保留 / 组播 / 未指定地址一律视为不可访问。"""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        # 解析不出合法 IP 的（比如畸形字面量）按不安全处理
        return True

    # ::ffff:127.0.0.1 这类 IPv4-mapped 地址在部分 Python 版本上 is_loopback
    # 判定为 False，先还原成 IPv4 再判，别让套壳地址绕过整张黑名单。
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped

    # 100.64.0.0/10 是运营商级 NAT（CGNAT）共享地址段，ipaddress 在 3.13
    # 之前不把它算作 is_private。服务端没有理由直连运营商内网，显式列出。
    if ip.version == 4 and ip in ipaddress.ip_network("100.64.0.0/10"):
        return True

    return (
        ip.is_private or ip.is_loopback or ip.is_link_local
        or ip.is_reserved or ip.is_multicast or ip.is_unspecified
    )


def validate_public_url(url: str, *, allow_private: bool | None = None) -> str:
    """校验一个待请求的 URL，返回原 URL；不安全则抛 ValueError。

    allow_private 为 None 时读 MP_ALLOW_PRIVATE_LLM_ENDPOINTS=1 开关。
    本地模型服务（Ollama/vLLM 跑在 127.0.0.1）是合理配置，所以留了这个
    显式逃生口，但默认必须是关的。
    """
    if allow_private is None:
        allow_private = os.environ.get("MP_ALLOW_PRIVATE_LLM_ENDPOINTS") == "1"

    if not isinstance(url, str) or not url.strip():
        raise ValueError("URL 为空")

    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"不允许的 URL 协议: {parsed.scheme!r}，仅支持 http/https")
    if parsed.username or parsed.password:
        raise ValueError("URL 不允许携带内嵌凭证")
    host = parsed.hostname
    if not host:
        raise ValueError("URL 缺少主机名")

    if allow_private:
        return url

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise ValueError(f"无法解析主机: {host}") from e
    for info in infos:
        ip = info[4][0]
        if is_blocked_ip(ip):
            raise ValueError(
                f"主机解析到内网/环回地址({ip})，已阻断；"
                "如确需访问内网服务，请设置 MP_ALLOW_PRIVATE_LLM_ENDPOINTS=1"
            )
    return url


def safe_output_path(base_dir: str | os.PathLike, *parts: str) -> Path:
    """把 parts 逐段拼到 base_dir 下并收敛校验，返回解析后的 Path。

    写入路径几乎都是"目录 + 一个变量名"拼出来的，而那个变量名可能来自
    用户输入（搜索关键词、task_id）。一旦它含上级引用或是绝对路径，
    open() 就会写到预期目录外面去。

    拼接放在这个函数里做，调用方就递不出一个未校验的完整路径：每一段
    必须恰好是一个路径分量（不含分隔符、不是绝对路径、不是上级引用），
    拼完再解析一次真实路径，确认结果仍落在 base_dir 之内——这一道会连
    符号链接绕出和"用绝对路径顶掉前缀"一起挡掉。
    """
    base = Path(base_dir).resolve()

    cleaned = []
    for part in parts:
        p = Path(part)
        if p.is_absolute() or os.pardir in p.parts or len(p.parts) != 1:
            raise ValueError(f"非法的路径分量: {part!r}")
        cleaned.append(part)

    target = base.joinpath(*cleaned).resolve()
    if target != base and base not in target.parents:
        raise ValueError(f"路径越出基准目录 {base}")
    return target


def safe_write_path(path: str | os.PathLike) -> Path:
    """校验一个调用方直接给出的完整写入路径。

    输出目录本身可以由配置决定（比如 config 里的 results_dir），那是明确
    的配置意图，不该被拦；但路径里任何一段都不允许是上级引用。解析时
    沿符号链接走，所以指向目录外的软链也会在这里露出来。
    """
    p = Path(path)
    if os.pardir in p.parts:
        raise ValueError(f"路径含上级引用，已拒绝: {path}")
    return p.resolve()
