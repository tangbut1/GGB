import time

from .. import config as cfg


class LLMHost:
    def __init__(self, config: dict):
        self.config = config

    def generate_guidance(self, forum_context: str) -> str:
        if not self.config:
            return ""
        api_key = self.config.get("api_key", "")
        if not api_key:
            return "【HOST提示】：未配置Host LLM，无法生成引导。"

        system_prompt = (
            "你是一个专业的金融市场分析论坛主持人 (Host)。当前参与的专家有：CollectAgent, SentimentAgent, TrendAgent。\n"
            "请你作为主持人履行职责：\n"
            "1. 用一段简短专业的话，总结各方专家的核心发现。\n"
            "2. 明确 @ 特定的 Agent，给出下一轮的重点关注方向。\n"
            "严格输出格式：\n"
            "【总结】：...\n"
            "【盲区引导】：@AgentName ..."
        )

        endpoint = self._endpoint()
        model = self.config.get("model", cfg.agent_model("forum_host"))
        timeout = int(self.config.get("timeout", cfg.agent_timeout("forum_host")))
        max_retries = int(self.config.get("max_retries", cfg.agent_max_retries("forum_host")))

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"以下是最近的讨论记录：\n{forum_context}"},
            ],
            "temperature": float(self.config.get("temperature", cfg.agent_temperature("forum_host"))),
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        last_error = ""
        for attempt in range(max_retries + 1):
            try:
                import requests
                response = requests.post(endpoint, headers=headers, json=payload, timeout=timeout)
                if response.status_code in (401, 403):
                    return "【HOST提示】：API 鉴权失败，请检查论坛主持人 API Key 配置。跳过本轮 Host 引导。"
                if response.status_code == 429:
                    time.sleep(min(2 ** attempt, 8))
                    continue
                response.raise_for_status()
                data = response.json()
                if "choices" in data and len(data["choices"]) > 0:
                    return data["choices"][0]["message"]["content"].strip()
                return "【HOST错误】：API返回异常"
            except Exception as e:
                last_error = str(e)
                if attempt < max_retries:
                    time.sleep(min(2 ** attempt, 4))
        return f"【HOST错误】：{last_error}"

    def _endpoint(self) -> str:
        base = str(self.config.get("base_url", cfg.agent_base_url("forum_host"))).rstrip("/")
        if not base.endswith("/chat/completions"):
            base = f"{base}/chat/completions"
        return base
