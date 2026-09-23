"""Tests for the forum judge (LLMHost): verdict parsing, sanitization,
heuristic fallback, context normalization and endpoint validation."""

import json

import pytest

from src.forum.llm_host import LLMHost, validate_endpoint

# 占位符凭据：仅用于验证“密钥无效/端点不可达时走兜底”，不是任何真实密钥
_PLACEHOLDER_KEY = "invalid-placeholder-key"
_ENDPOINT = "https://api.openai.com/v1"


# ---------------------------------------------------------------------------
# Verdict JSON parsing & sanitization
# ---------------------------------------------------------------------------

def test_parse_verdict_plain_json():
    raw = json.dumps({
        "stance": "negative", "confidence": 0.82,
        "summary": "风险大于机会", "key_disagreements": ["分歧1", "分歧2"],
        "red_strongest": "红方观点", "blue_strongest": "蓝方观点",
        "action_signal": "watch_out", "recommendation": "谨慎",
    }, ensure_ascii=False)
    verdict = LLMHost._parse_verdict_json(raw)
    assert verdict["stance"] == "negative"
    assert verdict["confidence"] == 0.82
    assert verdict["action_signal"] == "watch_out"
    assert verdict["key_disagreements"] == ["分歧1", "分歧2"]


def test_parse_verdict_strips_code_fences_and_prose():
    raw = ("好的，以下是裁定：\n```json\n"
           + json.dumps({"stance": "positive", "confidence": 0.5,
                         "summary": "看多", "action_signal": "buy_attention"},
                        ensure_ascii=False)
           + "\n```\n以上。")
    verdict = LLMHost._parse_verdict_json(raw)
    assert verdict["stance"] == "positive"
    assert verdict["action_signal"] == "buy_attention"


def test_parse_verdict_returns_empty_on_garbage():
    assert LLMHost._parse_verdict_json("【HOST错误】：端点校验失败") == {}
    assert LLMHost._parse_verdict_json("") == {}
    assert LLMHost._parse_verdict_json('{"no_stance": 1}') == {}


def test_sanitize_verdict_clamps_out_of_range_values():
    sanitized = LLMHost._sanitize_verdict({
        "stance": "BULLISH",          # 非法取值 → neutral
        "confidence": 7.5,            # 越界 → 1.0
        "action_signal": "moon",      # 非法取值 → neutral
        "key_disagreements": ["a"] * 10,   # 截断到 3 条
        "summary": "x" * 500,               # 截断到 200 字
    })
    assert sanitized["stance"] == "neutral"
    assert sanitized["confidence"] == 1.0
    assert sanitized["action_signal"] == "neutral"
    assert len(sanitized["key_disagreements"]) == 3
    assert len(sanitized["summary"]) == 200


def test_sanitize_verdict_handles_missing_fields():
    sanitized = LLMHost._sanitize_verdict({})
    assert sanitized["stance"] == "neutral"
    assert sanitized["confidence"] == 0.5
    assert sanitized["key_disagreements"] == []


# ---------------------------------------------------------------------------
# Heuristic fallback verdict (judge LLM unavailable)
# ---------------------------------------------------------------------------

def test_fallback_verdict_is_negative_when_red_dominates():
    red = "风险 风险 危机 负面 崩 下跌 警告"
    blue = "机会"
    verdict = LLMHost._fallback_verdict("测试", red, blue)
    assert verdict["stance"] == "negative"
    assert verdict["action_signal"] == "watch_out"
    assert verdict["confidence"] == 0.4
    assert "裁判 LLM" in verdict["summary"]


def test_fallback_verdict_is_positive_when_blue_dominates():
    red = "谨慎"
    blue = "机会 利好 反弹 增长 破局 正面"
    verdict = LLMHost._fallback_verdict("测试", red, blue)
    assert verdict["stance"] == "positive"
    assert verdict["action_signal"] == "buy_attention"


def test_fallback_verdict_neutral_when_balanced():
    verdict = LLMHost._fallback_verdict("测试", "风险", "机会")
    assert verdict["stance"] == "neutral"
    assert verdict["action_signal"] == "neutral"


def test_render_verdict_never_raises_without_network():
    """render_verdict must return a usable dict even when the LLM is unreachable."""
    cfg = {"api_key": _PLACEHOLDER_KEY, "base_url": _ENDPOINT}
    host = LLMHost(cfg)
    verdict = host.render_verdict(keyword="测试", red_text="风险 危机",
                                  blue_text="机会 利好", guidance="【总结】：x")
    assert verdict["stance"] in ("negative", "neutral", "positive")
    assert 0.0 <= verdict["confidence"] <= 1.0


# ---------------------------------------------------------------------------
# Guidance context normalization
# ---------------------------------------------------------------------------

def test_generate_guidance_returns_empty_without_config():
    host = LLMHost({})
    assert host.generate_guidance([{"agent": "SentimentAgent", "content": "x"}]) == ""


def test_normalize_context_accepts_dicts_lines_and_strings():
    structured = [{"agent": "SentimentAgent", "content": "红方发言"},
                  {"agent": "SYSTEM", "content": "系统消息"},
                  {"agent": "HOST", "content": "裁判消息"},
                  {"agent": "TrendAgent", "content": ""}]
    normalized = LLMHost._normalize_context(structured)
    assert normalized == [{"agent": "SentimentAgent", "content": "红方发言"}]

    lines = ["[2025-01-01 10:00:00] [SentimentAgent] [Round 1] 红方发言",
             "[2025-01-01 10:00:01] [SYSTEM] [Round 1] 系统消息"]
    assert LLMHost._normalize_context(lines) == [
        {"agent": "Unknown", "content": lines[0]}]

    assert LLMHost._normalize_context("一段纯文本") == [
        {"agent": "Unknown", "content": "一段纯文本"}]
    assert LLMHost._normalize_context(None) == []


# ---------------------------------------------------------------------------
# Endpoint validation (SSRF guard)
# ---------------------------------------------------------------------------

def test_validate_endpoint_rejects_bad_scheme_and_credentials():
    with pytest.raises(ValueError):
        validate_endpoint("ftp://example.com/v1")
    with pytest.raises(ValueError):
        validate_endpoint("https://user:pass@example.com/v1")
    with pytest.raises(ValueError):
        validate_endpoint("not-a-url")


def test_validate_endpoint_rejects_private_addresses():
    with pytest.raises(ValueError):
        validate_endpoint("http://127.0.0.1:11434/v1")
    with pytest.raises(ValueError):
        validate_endpoint("http://192.168.1.10:8000/v1")


def test_validate_endpoint_allows_public_host():
    # 走 DNS 解析；断网环境下会抛“无法解析”，两种情况都不是放行内网
    try:
        assert validate_endpoint(_ENDPOINT) == _ENDPOINT
    except ValueError as e:
        assert "无法解析" in str(e) or "内网" in str(e)


def test_validate_endpoint_opt_out_allows_local_model_server(monkeypatch):
    monkeypatch.setenv("MP_ALLOW_PRIVATE_LLM_ENDPOINTS", "1")
    assert validate_endpoint("http://127.0.0.1:11434/v1") == "http://127.0.0.1:11434/v1"
