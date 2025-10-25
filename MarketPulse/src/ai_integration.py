import os
from typing import Any, Dict, List, Literal, Optional

import requests

Provider = Literal["openai", "meta", "huggingface", "custom", "none"]


class AIClient:
    HF_DEFAULT_CLASSIFIER = "voidful/albert_chinese_small_sentiment"
    HF_DEFAULT_GENERATOR = "uer/gpt2-chinese-cluecorpussmall"

    def __init__(
        self,
        provider: Provider = "none",
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        generation_model: Optional[str] = None,
    ) -> None:
        self.provider: Provider = provider
        self.model: Optional[str] = model
        self.api_key: Optional[str] = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("HF_TOKEN")
        self.endpoint: Optional[str] = endpoint
        self.generation_model: Optional[str] = generation_model or os.getenv("HF_GENERATION_MODEL")

        self._hf_classifier = None
        self._hf_generator = None

    @staticmethod
    def auto_detect() -> "AIClient":
        if os.getenv("OPENAI_API_KEY"):
            return AIClient(
                provider="openai",
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                generation_model=os.getenv("OPENAI_MODEL"),
            )
        if os.getenv("META_ENDPOINT") and os.getenv("META_TOKEN"):
            return AIClient(
                provider="meta",
                model=os.getenv("META_MODEL", "llama-3-8b-instruct"),
                api_key=os.getenv("META_TOKEN"),
                endpoint=os.getenv("META_ENDPOINT"),
            )
        if os.getenv("HF_TOKEN"):
            return AIClient(
                provider="huggingface",
                model=os.getenv("HF_MODEL", AIClient.HF_DEFAULT_CLASSIFIER),
                generation_model=os.getenv("HF_GENERATION_MODEL", AIClient.HF_DEFAULT_GENERATOR),
            )
        # 默认为 HuggingFace 的公开模型（无需令牌）
        return AIClient(
            provider="huggingface",
            model=AIClient.HF_DEFAULT_CLASSIFIER,
            generation_model=AIClient.HF_DEFAULT_GENERATOR,
        )

    # ------------------------------------------------------------------
    # Sentiment classification
    # ------------------------------------------------------------------
    def classify_sentiment(self, texts: List[str]) -> List[float]:
        if not texts:
            return []
        if self.provider == "none":
            return [0.0 for _ in texts]
        if self.provider == "openai":
            return self._classify_with_openai(texts)
        if self.provider == "huggingface":
            scores = self._classify_with_huggingface(texts)
            if scores:
                return scores
            return self._rule_based_scores(texts)
        if self.provider == "custom":
            return self._classify_with_custom_endpoint(texts)
        return self._rule_based_scores(texts)

    def _classify_with_openai(self, texts: List[str]) -> List[float]:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        url = os.getenv("OPENAI_CHAT_URL", "https://api.openai.com/v1/chat/completions")
        outputs: List[float] = []
        for chunk in _batch(texts, 8):
            prompt = "\n".join([f"[{i}] {t}" for i, t in enumerate(chunk)])
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "Return sentiment scores in [-1,1] as JSON list only."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.0,
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()
            outputs.extend(_safe_parse_scores(content, len(chunk)))
        return outputs

    def _classify_with_huggingface(self, texts: List[str]) -> List[float]:
        try:
            classifier = self._get_hf_classifier()
        except Exception:
            return []

        scores: List[float] = []
        for chunk in _batch(texts, 16):
            try:
                result = classifier(list(chunk), truncation=True)
            except Exception:
                scores.extend([0.0] * len(chunk))
                continue

            if isinstance(result, list) and result and isinstance(result[0], list):
                # top_k=1 格式 [[{label, score}], ...]
                result = [item[0] for item in result if item]

            for item in result:
                label = str(item.get("label", "")).lower()
                score = float(item.get("score", 0.0))
                value = 0.0
                if any(tok in label for tok in ("neg", "负", "bear", "bad")):
                    value = -score
                elif any(tok in label for tok in ("pos", "正", "bull", "good")):
                    value = score
                elif "neu" in label or "中" in label:
                    value = 0.0
                else:
                    value = (score - 0.5) * 2
                scores.append(max(-1.0, min(1.0, value)))
        return scores

    def _classify_with_custom_endpoint(self, texts: List[str]) -> List[float]:
        if not self.endpoint:
            return [0.0 for _ in texts]
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        outputs: List[float] = []
        try:
            for chunk in _batch(texts, 16):
                payload = {"texts": list(chunk)}
                resp = requests.post(self.endpoint, json=payload, headers=headers, timeout=60)
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, dict):
                    data = data.get("scores") or data.get("data") or data.get("result")
                if isinstance(data, list):
                    values = [max(-1.0, min(1.0, float(x))) for x in data]
                    if len(values) == len(chunk):
                        outputs.extend(values)
                        continue
                outputs.extend([0.0] * len(chunk))
        except Exception:
            return [0.0 for _ in texts]
        return outputs

    def _rule_based_scores(self, texts: List[str]) -> List[float]:
        scores: List[float] = []
        positive_words = ("上涨", "增长", "利好", "创新", "盈利")
        negative_words = ("下跌", "亏损", "利空", "危机", "风险")
        for text in texts:
            text = text or ""
            pos = sum(word in text for word in positive_words)
            neg = sum(word in text for word in negative_words)
            length = max(len(text), 1)
            score = (pos - neg) / length * 10
            scores.append(max(-1.0, min(1.0, score)))
        return scores

    # ------------------------------------------------------------------
    # Narrative generation
    # ------------------------------------------------------------------
    def generate_insights(
        self,
        sentiment_summary: Dict[str, Any],
        trend_summary: Dict[str, Any],
    ) -> Dict[str, str]:
        narrative = self._rule_based_commentary(sentiment_summary, trend_summary)
        if self.provider != "huggingface":
            return narrative

        try:
            generator = self._get_hf_generator()
            pad_token_id = generator.tokenizer.pad_token_id or generator.tokenizer.eos_token_id
        except Exception:
            return narrative

        prompts = {
            "analysis_commentary": self._build_analysis_prompt(sentiment_summary),
            "trend_commentary": self._build_trend_prompt(trend_summary),
        }

        for key, prompt in prompts.items():
            try:
                outputs = generator(
                    prompt,
                    max_new_tokens=160,
                    do_sample=False,
                    temperature=0.7,
                    top_p=0.9,
                    return_full_text=False,
                    pad_token_id=pad_token_id,
                )
                if outputs:
                    text = outputs[0].get("generated_text", "").strip()
                    if text:
                        narrative[key] = text
            except Exception:
                continue
        return narrative

    def _build_analysis_prompt(self, sentiment_summary: Dict[str, Any]) -> str:
        total = sentiment_summary.get("total_news", 0)
        positives = sentiment_summary.get("positive_count", 0)
        negatives = sentiment_summary.get("negative_count", 0)
        neutral = sentiment_summary.get("neutral_count", 0)
        avg = sentiment_summary.get("avg_sentiment", 0.0)
        return (
            "请根据以下市场情绪统计数据，用中文生成一段不超过150字的分析摘要，"
            "风格专业、客观，并包含对投资者的情绪理解。\n"
            f"总新闻数: {total}\n积极新闻: {positives}\n消极新闻: {negatives}\n中性新闻: {neutral}\n"
            f"平均情绪得分: {avg:.3f}"
        )

    def _build_trend_prompt(self, trend_summary: Dict[str, Any]) -> str:
        if trend_summary.get("status") != "success":
            reason = trend_summary.get("message", "数据量不足，无法输出趋势建议。")
            return f"趋势模型未能成功运行，原因：{reason}。请简要说明对市场情绪的影响。"
        direction = trend_summary.get("trend_direction", "neutral")
        confidence = trend_summary.get("confidence", 0.0)
        recommendation = trend_summary.get("recommendation", "")
        return (
            "请根据以下趋势预测信息，生成一段不超过150字的市场情绪走向解读，"
            "语言客观简洁。\n"
            f"趋势方向: {direction}\n预测置信度: {confidence:.1%}\n建议: {recommendation}"
        )

    def _rule_based_commentary(
        self, sentiment_summary: Dict[str, Any], trend_summary: Dict[str, Any]
    ) -> Dict[str, str]:
        total = sentiment_summary.get("total_news", 0)
        avg = sentiment_summary.get("avg_sentiment", 0.0)
        positives = sentiment_summary.get("positive_count", 0)
        negatives = sentiment_summary.get("negative_count", 0)
        neutral = sentiment_summary.get("neutral_count", 0)

        if avg > 0.1:
            mood = "整体偏向积极，投资者风险偏好有所抬升"
        elif avg < -0.1:
            mood = "整体偏向谨慎，投资者倾向于规避风险"
        else:
            mood = "整体持中性态度，市场情绪较为平稳"

        analysis = (
            f"本次分析覆盖 {total} 条新闻，积极/消极/中性新闻分别为 {positives}/{negatives}/{neutral}。"
            f"综合情绪得分 {avg:.3f}，{mood}。"
        )

        if trend_summary.get("status") == "success":
            direction = trend_summary.get("trend_direction", "neutral")
            confidence = trend_summary.get("confidence", 0.0)
            recommendation = trend_summary.get("recommendation", "保持关注市场动态")
            trend = (
                f"模型判断情绪趋势趋向 {direction}，置信度约 {confidence:.1%}，"
                f"建议 {recommendation}。"
            )
        else:
            message = trend_summary.get("message", "数据不足，无法获得趋势预测结果。")
            trend = f"趋势预测未完成：{message}"

        return {"analysis_commentary": analysis, "trend_commentary": trend}

    # ------------------------------------------------------------------
    # HuggingFace helpers
    # ------------------------------------------------------------------
    def _get_hf_classifier(self):
        if self._hf_classifier is None:
            from transformers import pipeline  # type: ignore

            model_name = self.model or self.HF_DEFAULT_CLASSIFIER
            self._hf_classifier = pipeline(
                "text-classification",
                model=model_name,
                top_k=1,
                truncation=True,
            )
        return self._hf_classifier

    def _get_hf_generator(self):
        if self._hf_generator is None:
            from transformers import pipeline  # type: ignore

            model_name = self.generation_model or self.HF_DEFAULT_GENERATOR
            self._hf_generator = pipeline("text-generation", model=model_name)
            tokenizer = self._hf_generator.tokenizer
            if tokenizer.pad_token is None and tokenizer.eos_token is not None:
                tokenizer.pad_token = tokenizer.eos_token
        return self._hf_generator


def _batch(seq: List[str], size: int):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def _safe_parse_scores(content: str, expected: int) -> List[float]:
    try:
        import json

        data = json.loads(content)
        if isinstance(data, list):
            vals = [max(-1.0, min(1.0, float(x))) for x in data]
            if len(vals) == expected:
                return vals
    except Exception:
        pass
    return [0.0] * expected
