import json
import re
import time
from dataclasses import dataclass, field
from typing import Dict, Any, Optional

import requests

@dataclass
class AgentResult:
    status: str
    agent: str
    data: dict = field(default_factory=dict)
    summary: str = ""
    error: Optional[str] = None

    def to_dict(self) -> dict:
        res = {
            "status": self.status,
            "agent": self.agent,
            "data": self.data,
            "summary": self.summary,
        }
        if self.error is not None:
            res["error"] = self.error
        return res

class LLMClient:
    """LLM client with connection pooling and retries."""
    def __init__(self):
        self.session = requests.Session()

    def call_llm(self, model: str, base_url: str, api_key: str, system_prompt: str, user_prompt: str, temperature: float = 0.7, timeout: int = 60, max_retries: int = 3) -> str:
        if not api_key:
            return "Error: API Key is missing in configuration."

        endpoint = base_url.rstrip("/")
        if not endpoint.endswith("/chat/completions"):
            endpoint = f"{endpoint}/chat/completions"

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        last_error = ""
        for attempt in range(max_retries + 1):
            try:
                response = self.session.post(endpoint, headers=headers, json=payload, timeout=timeout)
                if response.status_code in (401, 403):
                    return "Error: API鉴权失败，请检查 API Key 配置。"
                if response.status_code == 429:
                    wait = min(2 ** attempt, 8)
                    time.sleep(wait)
                    continue
                response.raise_for_status()
                data = response.json()
                if "choices" in data and len(data["choices"]) > 0:
                    return data["choices"][0]["message"]["content"].strip()
                return f"Error: Unexpected response format: {data}"
            except Exception as e:
                last_error = str(e)
                if attempt < max_retries:
                    time.sleep(min(2 ** attempt, 4))
        return f"Error: 网络异常或超时，请稍后重试。详情: {last_error}"

# Shared client instance
_shared_llm_client = LLMClient()

def call_llm(model: str, base_url: str, api_key: str, system_prompt: str, user_prompt: str, temperature: float = 0.7, timeout: int = 60, max_retries: int = 3) -> str:
    return _shared_llm_client.call_llm(model, base_url, api_key, system_prompt, user_prompt, temperature, timeout, max_retries)


def _parse_markdown_insights(text: str, keyword: str) -> dict:
    """Fallback parsing for Markdown-structured responses (## Headings)."""
    if not text or "{" in text:
        return {}

    has_headings = bool(re.search(r'^#{1,4}\s+', text, re.MULTILINE))
    if not has_headings:
        return {}

    headline_match = re.search(r'^#{1,2}\s*(?:[\d.]+\s*)?(.+?)$', text, re.MULTILINE)
    headline = headline_match.group(1).strip()[:25] if headline_match else f"{keyword}舆情洞察"

    sections = re.split(r'\n(?=#{2,4}\s+)', text)
    insights = []
    type_keywords = {
        "opportunity": ["机会", "利好", "正面", "优势", "增长"],
        "risk": ["风险", "危机", "负面", "威胁", "隐患", "问题"],
        "anomaly": ["异常", "反常识", "反共识", "意外", "矛盾", "反常", "悖论", "泡沫"],
        "trend": ["趋势", "走向", "方向", "预测", "前景"],
    }

    for sec in sections:
        title_match = re.search(r'^#{2,4}\s*(?:[\d.]+\s*)?(.+?)$', sec, re.MULTILINE)
        if not title_match:
            continue
        heading_level = len(title_match.group(0)) - len(title_match.group(0).lstrip('#'))
        title = title_match.group(1).strip()[:20]
        if heading_level <= 2:
            continue
        
        body_start = title_match.end()
        body = sec[body_start:].strip()
        body = re.sub(r'\n+', ' ', body)[:120]

        ins_type = "trend"
        for t, kws in type_keywords.items():
            if any(kw in title + body for kw in kws):
                ins_type = t
                break

        contrarian = any(w in title + body for w in ["反直觉", "反共识", "悖论", "异常", "表面", "隐藏"])
        conf_match = re.search(r'(\d{1,3})%', body)
        confidence = float(int(conf_match.group(1)) / 100) if conf_match else 0.6

        if len(body) > 10:
            insights.append({
                "type": ins_type,
                "title": title[:8],
                "claim": body[:60],
                "evidence": body[:100],
                "why_now": "基于当前舆情数据实时分析",
                "confidence": min(0.95, max(0.1, confidence)),
                "contrarian": contrarian,
            })

    if len(insights) < 2:
        return {}

    neg_words = sum(1 for w in ["风险", "危机", "负面", "下跌", "崩"] if w in text)
    pos_words = sum(1 for w in ["机会", "利好", "增长", "正面", "突破"] if w in text)
    if neg_words > pos_words + 1:
        action_signal = "watch_out"
    elif pos_words > neg_words + 2:
        action_signal = "buy_attention"
    elif neg_words > 0 and pos_words > 0:
        action_signal = "neutral"
    else:
        action_signal = "neutral"

    blind_spots = []
    for sent in re.split(r'[。\n]', text):
        sent = sent.strip()
        if ("?" in sent or "？" in sent) and len(sent) > 8:
            blind_spots.append(sent[:80])

    return {
        "headline": headline,
        "action_signal": action_signal,
        "insights": insights[:6],
        "blind_spots": blind_spots[:3] or ["现有数据时间跨度有限，长期趋势待验证"],
        "one_week_prediction": "",
    }


def parse_llm_json(response: str, keyword: str = "") -> dict:
    """4-level fallback parsing logic for extracting JSON from LLM response."""
    response = (response or "").strip()

    # Level 1: Strip markdown code blocks
    if response.startswith("```"):
        response = re.sub(r"^```(?:json)?\s*\n?", "", response)
        response = re.sub(r"\n?```\s*$", "", response)
        response = response.strip()

    # Level 2: Direct parse
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass

    # Level 3: Find first { to last }
    first_brace = response.find("{")
    last_brace = response.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        json_candidate = response[first_brace:last_brace + 1]
        try:
            return json.loads(json_candidate)
        except json.JSONDecodeError:
            pass

    # Level 4: Regex search for any dict-like structure
    match = re.search(r'\{.*\}', response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # Level 5: Markdown parsing (if any structure)
    md_parsed = _parse_markdown_insights(response, keyword)
    if md_parsed:
        return md_parsed

    return {}
