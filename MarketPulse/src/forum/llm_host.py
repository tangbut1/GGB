import json
import re

import requests

from ..net_safety import validate_public_url


def validate_endpoint(url: str) -> str:
    """Validate an operator-configured LLM endpoint before any request.

    Guards against SSRF via a tampered config: scheme whitelist, no embedded
    credentials, and DNS results must not point inside the private network.
    Local model servers (Ollama/vLLM on 127.0.0.1) are a legitimate setup, so
    they can be re-enabled explicitly with MP_ALLOW_PRIVATE_LLM_ENDPOINTS=1.

    判定逻辑与采集器抓正文时的地址校验同源，见 src/net_safety.py。
    """
    return validate_public_url(url)


def post_llm_json(endpoint: str, payload: dict, headers: dict,
                  timeout: int = 60):
    """POST 一个 LLM 端点，返回解析后的 JSON。

    BaseAgent、LLMHost、ai_integration 三处都在发同一个 OpenAI 兼容请求。
    各写一遍就容易漏掉 allow_redirects=False——一个校验过的公网地址 302
    跳到内网，入口那道校验就全废了。

    校验放在这个函数里而不是留给调用方：它拥有唯一的请求出口，调用方
    漏掉一步就等于没校验。需要"校验失败就走兜底逻辑"的调用方可以自己
    先调一次 validate_endpoint，这里再过一遍不依赖那个顺序。
    """
    endpoint = validate_endpoint(endpoint)
    resp = requests.post(
        endpoint, headers=headers, json=payload,
        timeout=timeout, allow_redirects=False,
    )
    resp.raise_for_status()
    return resp.json()


class LLMHost:
    """Forum moderator / judge.

    Two duties:
    - ``generate_guidance()``: between debate rounds, point out the core
      disagreement between the red (crisis) and blue (rational) analysts and
      ask pointed questions to drive the rebuttal round.
    - ``render_verdict()``: after the debate, deliver a structured final
      verdict (stance, confidence, key disagreements, recommendation).
    """

    def __init__(self, config: dict):
        self.config = config or {}

    # ── helpers ──────────────────────────────────────────────────────
    def _endpoint(self) -> str:
        base_url = self.config.get("base_url", "https://api.openai.com/v1")
        endpoint = base_url.rstrip("/")
        if not endpoint.endswith("/chat/completions"):
            endpoint = f"{endpoint}/chat/completions"
        return endpoint

    def _post(self, messages: list, temperature: float = 0.7):
        """POST chat messages; returns (content, usage). Never raises."""
        api_key = self.config.get("api_key", "")
        if not api_key:
            return "【HOST错误】：未配置 Host LLM 的 API Key。", {}

        try:
            endpoint = validate_endpoint(self._endpoint())
        except ValueError as e:
            return f"【HOST错误】：端点校验失败: {e}", {}

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.config.get("model", "gpt-4o-mini"),
            "messages": messages,
            "temperature": temperature,
        }
        try:
            response = requests.post(
                endpoint, headers=headers, json=payload,
                timeout=60, allow_redirects=False,
            )
            response.raise_for_status()
            data = response.json()
            usage = data.get("usage", {}) or {}
            if "choices" in data and len(data["choices"]) > 0:
                return data["choices"][0]["message"]["content"].strip(), usage
            return "【HOST错误】：API 返回格式异常", usage
        except Exception as e:
            return f"【HOST错误】：{str(e)}", {}

    @staticmethod
    def _normalize_context(forum_messages) -> list:
        """Accept structured dicts, raw log lines, or a plain string."""
        if not forum_messages:
            return []
        if isinstance(forum_messages, str):
            return [{"agent": "Unknown", "content": forum_messages}]
        normalized = []
        for msg in forum_messages:
            if isinstance(msg, dict):
                agent = msg.get("agent", "Unknown")
                content = msg.get("content", "")
                if agent in ("SYSTEM", "HOST") or not content:
                    continue
                normalized.append({"agent": agent, "content": content})
            elif isinstance(msg, str):
                line = msg.strip()
                if not line or "[SYSTEM]" in line or "[HOST]" in line or "--- Forum" in line:
                    continue
                normalized.append({"agent": "Unknown", "content": line})
        return normalized

    # ── between-round guidance ───────────────────────────────────────
    def generate_guidance(self, forum_messages) -> str:
        """Return the judge's mid-debate guidance text (never a tuple)."""
        if not self.config:
            return ""

        system_prompt = (
            "你是一个冷酷而极其理性的研判法官 (Judge / HOST)。当前参与辩论的专家有："
            "危机分析师(红方 SentimentAgent)、理性分析师(蓝方 TrendAgent)。\n"
            "你的职责不是平铺直叙地总结，而是去寻找红蓝双方的【逻辑漏洞和核心矛盾】！\n"
            "请你作为裁判长履行职责：\n"
            "1. 用一段简短专业的话，一针见血地指出红蓝双方最根本的分歧点"
            "（如：红方认为会崩盘，而蓝方认为基本面没坏）。\n"
            "2. 严厉地 @ 特定的 Agent，抛出刁钻的问题，逼迫他们在下一轮深挖"
            "（例如：@TrendAgent 你的数据不足以证明... 请回答...）。\n"
            "严格输出格式：\n"
            "【总结】：...\n"
            "【盲区引导】：@AgentName ..."
        )

        messages = [{"role": "system", "content": system_prompt}]
        for turn in self._normalize_context(forum_messages):
            messages.append({
                "role": "user",
                "name": turn["agent"],
                "content": turn["content"],
            })
        if len(messages) == 1:
            messages.append({"role": "user", "content": "暂无红蓝双方的发言记录。"})

        content, _usage = self._post(messages)
        return content

    # ── final verdict ────────────────────────────────────────────────
    def render_verdict(self, keyword: str, red_text: str, blue_text: str,
                       guidance: str = "") -> dict:
        """Structured final verdict over the whole debate.

        Always returns a dict — on LLM failure a heuristic fallback verdict
        is produced so downstream stages never break.
        """
        system_prompt = """你是一个 JSON 输出机，只输出一段合法 JSON，第一个字符是 {，最后一个字符是 }。

你是舆情辩论的终裁法官。红方是危机分析师（看空、放大风险），蓝方是理性分析师（看多、寻找破局点）。
请通读双方全部发言，输出最终裁定 JSON（不要输出任何 JSON 以外的内容）：
{
    "stance": "negative | neutral | positive",
    "confidence": 0.0到1.0之间的数字,
    "summary": "一段话总结整场辩论的核心分歧与裁定理由，不超过120字",
    "key_disagreements": ["红蓝双方最核心的分歧点1", "分歧点2"],
    "red_strongest": "红方最有说服力的观点，一句话",
    "blue_strongest": "蓝方最有说服力的观点，一句话",
    "action_signal": "watch_out | neutral | buy_attention",
    "recommendation": "给决策者的一句话建议，不超过50字"
}"""

        user_prompt = (
            f"分析主题：{keyword}\n\n"
            f"【红方（危机分析师）发言】\n{(red_text or '（无）')[:2000]}\n\n"
            f"【蓝方（理性分析师）发言】\n{(blue_text or '（无）')[:2000]}\n\n"
            f"【裁判中期引导】\n{(guidance or '（无）')[:800]}\n\n"
            "请输出最终裁定 JSON。"
        )

        content, _usage = self._post(
            [{"role": "system", "content": system_prompt},
             {"role": "user", "content": user_prompt}],
            temperature=0.3,
        )

        verdict = self._parse_verdict_json(content)
        if verdict:
            return verdict
        return self._fallback_verdict(keyword, red_text, blue_text)

    @staticmethod
    def _parse_verdict_json(text: str) -> dict:
        if not text:
            return {}
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*\n?", "", text)
            text = re.sub(r"\n?```\s*$", "", text).strip()
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "stance" in data:
                return LLMHost._sanitize_verdict(data)
        except json.JSONDecodeError:
            pass
        first, last = text.find("{"), text.rfind("}")
        if first != -1 and last > first:
            try:
                data = json.loads(text[first:last + 1])
                if isinstance(data, dict) and "stance" in data:
                    return LLMHost._sanitize_verdict(data)
            except json.JSONDecodeError:
                pass
        return {}

    @staticmethod
    def _sanitize_verdict(data: dict) -> dict:
        stance = str(data.get("stance", "neutral")).lower()
        if stance not in ("negative", "neutral", "positive"):
            stance = "neutral"
        try:
            confidence = min(1.0, max(0.0, float(data.get("confidence", 0.5))))
        except (TypeError, ValueError):
            confidence = 0.5
        signal = str(data.get("action_signal", "neutral")).lower()
        if signal not in ("watch_out", "neutral", "buy_attention"):
            signal = "neutral"

        def _as_list(value):
            if isinstance(value, list):
                return [str(v)[:80] for v in value[:3]]
            return [str(value)[:80]] if value else []

        return {
            "stance": stance,
            "confidence": round(confidence, 2),
            "summary": str(data.get("summary", ""))[:200],
            "key_disagreements": _as_list(data.get("key_disagreements")),
            "red_strongest": str(data.get("red_strongest", ""))[:120],
            "blue_strongest": str(data.get("blue_strongest", ""))[:120],
            "action_signal": signal,
            "recommendation": str(data.get("recommendation", ""))[:120],
        }

    @staticmethod
    def _pick_strongest(text: str) -> str:
        """从一方发言里挑信息密度最高的一句，作为"最有力论据"。

        不能按字数硬切原文：那样会把句子断在半中间（例如截出"时间跨"），
        终裁卡片上看着像乱码。优先选带具体数字的句子——有实测值的才叫论据。
        """
        if not text:
            return "（无）"
        candidates = [
            s.strip() for s in re.split(r"[。！？\n]", text)
            if len(s.strip()) >= 8
        ]
        if not candidates:
            return text[:80]

        def density(s: str):
            digits = sum(ch.isdigit() for ch in s)
            return digits, min(len(s), 90)

        best = max(candidates, key=density)
        # 段头（【红方立论】【数据底座】这类）是结构标记，跟着论据一起
        # 显示会让"最有力论据"看起来像在引用小标题。它和被引句子同在
        # 一行、中间没有句号，所以切分时不会被剥掉，这里单独去掉。
        best = re.sub(r"^\s*【[^】]{0,20}】\s*", "", best).strip()
        if len(best) <= 90:
            return best or "（无）"
        return best[:87] + "..."

    @staticmethod
    def _fallback_verdict(keyword: str, red_text: str, blue_text: str) -> dict:
        """Heuristic verdict when the judge LLM is unavailable."""
        red_neg = sum(red_text.count(w) for w in ("风险", "危机", "负面", "崩", "下跌", "警告"))
        blue_pos = sum(blue_text.count(w) for w in ("机会", "利好", "反弹", "增长", "破局", "正面"))
        if red_neg > blue_pos + 2:
            stance, signal = "negative", "watch_out"
        elif blue_pos > red_neg + 2:
            stance, signal = "positive", "buy_attention"
        else:
            stance, signal = "neutral", "neutral"
        return {
            "stance": stance,
            "confidence": 0.4,
            "summary": f"关于'{keyword}'的红蓝辩论已结束，裁判 LLM 暂不可用，"
                       f"以下裁定基于双方观点密度启发式生成，仅供参考。",
            "key_disagreements": ["裁判 LLM 未返回结构化分歧点"],
            "red_strongest": LLMHost._pick_strongest(red_text),
            "blue_strongest": LLMHost._pick_strongest(blue_text),
            "action_signal": signal,
            "recommendation": "建议人工复核双方论据后决策。",
        }
