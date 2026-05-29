import logging
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

from .. import config as cfg


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
        return self._call_llm_inner(system_prompt, user_prompt, temperature)

    def _call_llm_inner(self, system_prompt: str, user_prompt: str, temperature: float = 0.7) -> str:
        if not self.config:
            return "Error: No LLM configuration found for this agent."

        api_key = self.config.get("api_key", "")
        model = self.config.get("model", "gpt-4o-mini")
        if not api_key:
            return "Error: API Key is missing in configuration."

        endpoint = self._resolve_endpoint()
        timeout = int(self.config.get("timeout", cfg.agent_timeout(self.name)))
        max_retries = int(self.config.get("max_retries", cfg.agent_max_retries(self.name)))

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
                import requests
                response = requests.post(endpoint, headers=headers, json=payload, timeout=timeout)
                if response.status_code in (401, 403):
                    return f"[LLM不可用] API鉴权失败，请检查 {self.name} 的 API Key 配置。"
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
        return f"[LLM不可用] 调用 {self.name} 失败：网络异常或超时，请稍后重试。"

    def _resolve_endpoint(self) -> str:
        base_url = str(self.config.get("base_url", "")).rstrip("/")
        if not base_url:
            base_url = cfg.agent_base_url(self.name).rstrip("/")
        if not base_url.endswith("/chat/completions"):
            base_url = f"{base_url}/chat/completions"
        return base_url
