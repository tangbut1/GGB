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

        import datetime
        current_date_str = f"【系统提示：当前现实世界的本地时间是 {datetime.datetime.now().strftime('%Y年%m月%d日')}。你的分析必须基于当前时间尺度。】\n"
        
        system_prompt = current_date_str + (
            "你是一个冷酷而极其理性的研判法官 (Judge / HOST)。当前参与辩论的专家有：危机分析师(红方 SentimentAgent)、理性分析师(蓝方 TrendAgent)。\n"
            "你的职责不是平铺直叙地总结，而是去寻找红蓝双方的【逻辑漏洞和核心矛盾】！\n"
            "请你作为裁判长履行职责：\n"
            "1. 用一段简短专业的话，一针见血地指出红蓝双方最根本的分歧点（如：红方认为会崩盘，而蓝方认为基本面没坏）。\n"
            "2. 严厉地 @ 特定的 Agent，抛出刁钻的问题，逼迫他们在下一轮深挖（例如：@TrendAgent 你的数据不足以证明... 请回答...）。\n"
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
