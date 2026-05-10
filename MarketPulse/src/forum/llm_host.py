import requests

class LLMHost:
    def __init__(self, config: dict):
        self.config = config
        
    def generate_guidance(self, forum_context: str) -> str:
        if not self.config:
            return ""
            
        base_url = self.config.get("base_url", "https://api.openai.com/v1")
        api_key = self.config.get("api_key", "")
        model = self.config.get("model", "gpt-4o-mini")

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
        
        endpoint = base_url.rstrip("/")
        if not endpoint.endswith("/chat/completions"):
            endpoint = f"{endpoint}/chat/completions"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"以下是最近的讨论记录：\n{forum_context}"}
            ],
            "temperature": 0.7
        }

        try:
            response = requests.post(endpoint, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            if "choices" in data and len(data["choices"]) > 0:
                return data["choices"][0]["message"]["content"].strip()
            return "【HOST错误】：API返回异常"
        except Exception as e:
            return f"【HOST错误】：{str(e)}"
