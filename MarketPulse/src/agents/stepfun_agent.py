"""阶跃星辰（StepFun）Agent 客户端。

红蓝辩论本身跑在 deepseek 上（两个 agent 互相驳斥，需要快且便宜）。这个
客户端负责辩论之外、需要更强推理的独立环节：

  1. 追问的上下文补全 —— 用户问"蓝方的数据依据是什么"，要把论坛记录里
     蓝方的原话、裁判的引导、以及终裁一并塞进上下文，token 量大；
  2. 终裁的第二意见（可选）—— 用第三个模型复核裁判结论，避免单一模型
     的立场偏差一路带到结论。

设计约束：
  - 未配置 Key 时 `available()` 返回 False，调用方走原有 deepseek 路径，
    绝不让它变成硬依赖；
  - 所有失败都返回字符串错误而不是抛异常，和 BaseAgent 的约定一致；
  - 端点走 validate_endpoint 校验，防止配置被改成内网地址。
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

import requests

from ..forum.llm_host import validate_endpoint

DEFAULT_BASE_URL = "https://api.stepfun.com/v1"
DEFAULT_MODEL = "step-5-preview"


class StepFunAgent:
    """对 StepFun /chat/completions 的薄封装，只做本项目需要的两件事。"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        self.base_url = cfg.get("base_url") or DEFAULT_BASE_URL
        self.api_key = cfg.get("api_key") or ""
        self.model = cfg.get("model") or DEFAULT_MODEL
        self.temperature = float(cfg.get("temperature", 0.3))
        self.timeout = int(cfg.get("timeout", 90))

    # ── 状态 ────────────────────────────────────────────────────────
    def available(self) -> bool:
        """Key 到位才可用。占位符（${...} 没展开、your-api-key-here）不算。"""
        key = (self.api_key or "").strip()
        if not key or key.startswith("${") or key == "your-api-key-here":
            return False
        return True

    def describe(self) -> Dict[str, Any]:
        return {
            "provider": "stepfun",
            "model": self.model,
            "base_url": self.base_url,
            "configured": self.available(),
        }

    # ── 调用 ────────────────────────────────────────────────────────
    def _endpoint(self) -> str:
        endpoint = self.base_url.rstrip("/")
        if not endpoint.endswith("/chat/completions"):
            endpoint = f"{endpoint}/chat/completions"
        return validate_endpoint(endpoint)

    def complete(self, system_prompt: str, user_prompt: str,
                 temperature: Optional[float] = None) -> str:
        """一次性补全。失败返回以 "Error" 开头的字符串（不抛异常）。"""
        if not self.available():
            return "Error: StepFun Agent 未配置 API Key"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature if temperature is None else temperature,
            "stream": False,
        }
        try:
            resp = requests.post(
                self._endpoint(),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout,
                allow_redirects=False,
            )
            resp.raise_for_status()
            data = resp.json()
        except ValueError as e:
            # 端点校验失败（内网地址等）
            return f"Error: StepFun Agent 端点校验失败: {e}"
        except Exception as e:  # noqa: BLE001
            return f"Error: StepFun Agent 调用失败: {e}"

        choices = data.get("choices") or []
        if not choices:
            return f"Error: StepFun Agent 返回格式异常: {data}"
        content = (choices[0].get("message") or {}).get("content") or ""
        content = content.strip()
        if not content:
            return "Error: StepFun Agent 返回空内容"
        return content

    def stream(self, system_prompt: str, user_prompt: str,
               temperature: Optional[float] = None):
        """流式补全的生成器，逐段 yield 文本；出错 yield 以 "Error" 开头的串。"""
        if not self.available():
            yield "Error: StepFun Agent 未配置 API Key"
            return

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature if temperature is None else temperature,
            "stream": True,
        }
        try:
            resp = requests.post(
                self._endpoint(),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout,
                stream=True,
                allow_redirects=False,
            )
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                text = line.decode("utf-8", errors="replace")
                if not text.startswith("data:"):
                    continue
                chunk = text[5:].strip()
                if chunk == "[DONE]":
                    break
                try:
                    obj = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
                delta = (obj.get("choices") or [{}])[0].get("delta") or {}
                piece = delta.get("content") or ""
                if piece:
                    yield piece
        except ValueError as e:
            yield f"Error: StepFun Agent 端点校验失败: {e}"
        except Exception as e:  # noqa: BLE001
            yield f"Error: StepFun Agent 调用失败: {e}"

    # ── 业务封装 ────────────────────────────────────────────────────
    def build_followup_prompt(self, question: str,
                              context: Dict[str, Any]) -> tuple:
        """组装追问用的 (system, user) 两个 prompt。

        单独拆出来是为了让流式和非流式两条路径共用同一份上下文组装逻辑，
        否则改一处忘一处，流式回答就会丢证据样本。
        """
        keyword = context.get("keyword", "")
        conclusion = context.get("conclusion", "")
        verdict = context.get("verdict") or {}
        sentiment = context.get("sentiment_summary") or {}
        trend = context.get("trend_summary") or {}
        news = context.get("analyzed_news") or []

        evidence_lines: List[str] = []
        for i, n in enumerate(news[:15]):
            if not isinstance(n, dict):
                continue
            title = (n.get("title") or "").strip()
            if not title:
                continue
            src = n.get("source") or "未知来源"
            tier = n.get("source_tier_label") or "待核验"
            score = n.get("sentiment_score")
            score_txt = f"{score:+.2f}" if isinstance(score, (int, float)) else "N/A"
            evidence_lines.append(f"{i+1}. [{tier}|{src}|情绪{score_txt}] {title[:90]}")

        system_prompt = (
            "你是 MarketPulse 的舆情研判助手，服务于一个红蓝辩论分析系统。"
            "红方是危机分析师（看空），蓝方是趋势分析师（理性），裁判给出结构化终裁。\n"
            "回答用户追问时遵守：\n"
            "1. 只能使用下面提供的上下文里出现过的事实和数字，禁止编造或外推；\n"
            "2. 上下文没覆盖到就明说'现有数据不足以回答'，并指出缺什么；\n"
            "3. 涉及投资判断必须附风险提示；\n"
            "4. 用中文，结构化分段，200-400字。"
        )

        user_prompt = f"""【分析对象】{keyword or '（未提供）'}

【综合结论】
{conclusion or '（无）'}

【裁判终裁】
立场：{verdict.get('stance', '未知')}
置信度：{verdict.get('confidence', '未知')}
摘要：{verdict.get('summary', '（无）')}
核心分歧：{('；'.join(verdict.get('key_disagreements') or []) or '（无）')}
行动建议：{verdict.get('recommendation', '（无）')}

【情绪统计】共 {sentiment.get('total_news', 0)} 条，
负面 {sentiment.get('negative_count', 0)} / 中性 {sentiment.get('neutral_count', 0)} / 正面 {sentiment.get('positive_count', 0)}，
情绪均分 {sentiment.get('avg_sentiment', 0)}。
校正方式：{'大模型校正后的 SnowNLP 结果' if sentiment.get('llm_corrected') else 'SnowNLP 原始结果（大模型校正未生效）'}

【趋势】方向 {trend.get('trend_direction', '未知')}，
置信度 {trend.get('confidence', '未知')}，
数据质量 {trend.get('data_quality', '未知')}，
模型 {trend.get('model_type', '未知')}，观测点 {trend.get('data_points', 0)} 个。
数据说明：{trend.get('data_note', '（无）')}

【证据样本（含信源层级与情绪分）】
{chr(10).join(evidence_lines) or '（无）'}

【用户追问】
{question}"""

        return system_prompt, user_prompt

    def answer_followup(self, question: str, context: Dict[str, Any]) -> str:
        """基于完整分析上下文回答追问（非流式）。"""
        system_prompt, user_prompt = self.build_followup_prompt(question, context)
        return self.complete(system_prompt, user_prompt)


_JSON_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def extract_json(text: str) -> Optional[Dict[str, Any]]:
    """从模型回复里抠出 JSON 对象（容忍代码围栏和前后杂音）。"""
    if not text:
        return None
    cleaned = _JSON_FENCE.sub("", text.strip())
    try:
        obj = json.loads(cleaned)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(cleaned[start:end + 1])
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None
