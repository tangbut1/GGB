import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import requests

class BaseAgent(ABC):
    def __init__(self, name: str, config: Dict[str, Any], forum_manager: Optional[Any] = None):
        self.name = name
        self.config = config or {}
        self.forum = forum_manager
        self.system_prompt = self._get_system_prompt()
        self.iteration_count = 1

    @abstractmethod
    def _get_system_prompt(self) -> str:
        pass

    @abstractmethod
    def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        pass

    def write_to_forum_log(self, content: str) -> None:
        if self.forum:
            self.forum.write(agent_name=self.name, iteration=self.iteration_count, content=content)
        else:
            logging.info(f"[{self.name}] [Round {self.iteration_count}] {content}")

    def read_host_guidance(self) -> str:
        if self.forum:
            return self.forum.get_latest_host_guidance()
        return ""

    def call_llm(self, prompt: str, temperature: float = 0.7) -> str:
        return self._call_llm_inner(self.system_prompt, prompt, temperature)

    def call_llm_with_system(self, system_prompt: str, user_prompt: str, temperature: float = 0.7) -> str:
        """使用自定义 system prompt 调用 LLM，ReportAgent AI 解读专用"""
        return self._call_llm_inner(system_prompt, user_prompt, temperature)

    def _call_llm_inner(self, system_prompt: str, user_prompt: str, temperature: float = 0.7) -> str:
        if not self.config:
            return "Error: No LLM configuration found for this agent."

        base_url = self.config.get("base_url", "https://api.openai.com/v1")
        api_key = self.config.get("api_key", "")
        model = self.config.get("model", "gpt-4o-mini")

        if not api_key:
            return "Error: API Key is missing in configuration."

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        endpoint = base_url.rstrip("/")
        if not endpoint.endswith("/chat/completions"):
            endpoint = f"{endpoint}/chat/completions"

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": temperature
        }

        try:
            response = requests.post(endpoint, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            if "choices" in data and len(data["choices"]) > 0:
                return data["choices"][0]["message"]["content"].strip()
            return f"Error: Unexpected response format: {data}"
        except Exception as e:
            return f"Error calling LLM for {self.name}: {str(e)}"
