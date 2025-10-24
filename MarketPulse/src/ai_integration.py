import os
from typing import List, Literal, Optional

import requests


Provider = Literal["openai", "meta", "huggingface", "custom", "none"]


class AIClient:
    def __init__(self, provider: Provider = "none", model: Optional[str] = None, api_key: Optional[str] = None,
                 endpoint: Optional[str] = None) -> None:
        self.provider: Provider = provider
        self.model: Optional[str] = model
        self.api_key: Optional[str] = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("HF_TOKEN")
        self.endpoint: Optional[str] = endpoint

    @staticmethod
    def auto_detect() -> "AIClient":
        if os.getenv("OPENAI_API_KEY"):
            return AIClient(provider="openai", model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
        if os.getenv("META_ENDPOINT") and os.getenv("META_TOKEN"):
            return AIClient(provider="meta", model=os.getenv("META_MODEL", "llama-3-8b-instruct"),
                            api_key=os.getenv("META_TOKEN"), endpoint=os.getenv("META_ENDPOINT"))
        if os.getenv("HF_TOKEN"):
            return AIClient(provider="huggingface", model=os.getenv("HF_MODEL", "distilbert-base-uncased"))
        return AIClient(provider="none")

    def classify_sentiment(self, texts: List[str]) -> List[float]:
        if not texts:
            return []
        if self.provider == "none":
            # Fallback: neutral scores
            return [0.0 for _ in texts]
        if self.provider == "openai":
            # Minimal example using a prompt; replace with SDK if desired
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
        if self.provider == "huggingface":
            # Suggest using transformers pipeline if available locally; simple neutral fallback
            try:
                from transformers import pipeline  # type: ignore
                classifier = pipeline("sentiment-analysis", model=self.model)
                scores: List[float] = []
                for chunk in _batch(texts, 16):
                    result = classifier(list(chunk))
                    for r in result:
                        label = r["label"].lower()
                        score = float(r["score"]) if "score" in r else 0.5
                        scores.append(score if "pos" in label else (-score if "neg" in label else 0.0))
                return scores
            except Exception:
                return [0.0 for _ in texts]
        if self.provider == "custom":
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
                        scores = [max(-1.0, min(1.0, float(x))) for x in data]
                        if len(scores) == len(chunk):
                            outputs.extend(scores)
                            continue
                    outputs.extend([0.0] * len(chunk))
                return outputs
            except Exception:
                return [0.0 for _ in texts]
        if self.provider == "meta":
            # Placeholder for Meta endpoint usage
            return [0.0 for _ in texts]
        return [0.0 for _ in texts]


def _batch(seq: List[str], size: int):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


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


