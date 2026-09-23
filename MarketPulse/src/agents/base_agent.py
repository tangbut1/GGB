import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import requests

from ..forum.llm_host import validate_endpoint

class BaseAgent(ABC):
    def __init__(self, name: str, config: Dict[str, Any], forum_manager: Optional[Any] = None):
        self.name = name
        self.config = config or {}
        self.forum = forum_manager
        self.system_prompt = self._get_system_prompt()
        self.iteration_count = 1
        # 每个 agent 的超时与重试来自 config.yaml（src/config.py 已把
        # MP_{AGENT}_TIMEOUT / MP_{AGENT}_MAX_RETRIES 合进来）。推理型模型
        # 生成一篇危机研判很容易超过 60 秒，写死 60 会让长 prompt 的调用
        # 间歇性超时，表现为"LLM 校正没生效"这种看不出原因的降级。
        self.timeout = int(self.config.get("timeout", 120))
        self.max_retries = max(1, int(self.config.get("max_retries", 2)))

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

    @staticmethod
    def llm_unavailable(response: str) -> bool:
        """判断一次 LLM 调用是否实际失败。

        _call_llm_inner 的所有失败路径都返回以 "Error" 开头的字符串
        （未配置、缺 Key、网络异常、响应格式异常），空响应同理。
        降级逻辑必须和成功路径区分开：成功但内容不理想可以走启发式兜底，
        失败则必须原样保留本地算法结果，不能拿兜底值冒充模型结论。
        """
        return not response or not response.strip() or response.strip().startswith("Error")

    @staticmethod
    def extract_opponent_claim(feedback: str, limit: int = 240) -> str:
        """从主持人拼装的 feedback 中取出对方上一轮的发言片段。

        格式见 OrchestratorAgent._build_rebuttal_feedback：
        【主持人指引】…\n\n【{对方}上一轮观点，请逐一驳斥】\n{发言}\n\n请输出…
        降级模式下第二轮要靠它点名回应对方，否则两轮立论会一字不差。
        """
        if not feedback:
            return ""
        marker = "上一轮观点，请逐一驳斥】"
        idx = feedback.find(marker)
        if idx == -1:
            return ""
        claim = feedback[idx + len(marker):].strip()
        end = claim.find("\n\n请输出")
        if end != -1:
            claim = claim[:end]
        # 段头（【蓝方立论】这类）是结构标记而不是论据。带着它去引用，
        # "对方引用的"后面就跟一个小标题，读起来像在引用目录。
        claim = re.sub(r"【[^】]{0,20}】", "", claim)
        claim = " ".join(claim.split())
        if len(claim) <= limit:
            return claim
        # 超长必须按句末截断。硬切会把词断在中间——实测引文出现过
        # "时间跨"这种残句，终裁卡片上看着像乱码。优先找句号类边界，
        # 引文停在逗号上会像是话没说完，只有后半段确实没有句号时才退一步。
        cut = claim[:limit]
        for boundary in max(cut.rfind(p) for p in "。！？；"), cut.rfind("，"):
            if boundary >= limit // 2:
                return cut[: boundary + 1].strip()
        return cut.strip()

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

        # base_url 来自 config.yaml / 环境变量，属于"配置即输入"：被改成一个
        # 内网地址时，这里就是 SSRF 的出口。发请求前统一校验，与 LLMHost、
        # 采集器抓正文共用同一套判据（src/net_safety.py）。
        try:
            endpoint = validate_endpoint(endpoint)
        except ValueError as e:
            return f"Error calling LLM for {self.name}: 端点校验失败: {e}"

        import datetime
        current_date_str = f"【系统提示：当前现实世界的本地时间是 {datetime.datetime.now().strftime('%Y年%m月%d日')}。你的分析必须基于当前时间尺度。】\n"
        final_system_prompt = current_date_str + system_prompt

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": final_system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": temperature
        }

        try:
            # allow_redirects=False：endpoint 已经过 validate_endpoint 校验，
            # 但 requests 默认会跟随 302。放行跟随就等于放行"先指向公网、
            # 再跳内网"的绕过路径，与采集器 _safe_get 同一套判据。
            last_err = ""
            for attempt in range(self.max_retries):
                try:
                    response = requests.post(
                        endpoint, headers=headers, json=payload,
                        timeout=self.timeout, allow_redirects=False,
                    )
                    response.raise_for_status()
                    data = response.json()

                    # Report usage metrics if log manager is available
                    if self.forum and "usage" in data:
                        self.forum.add_usage(data["usage"])

                    if "choices" in data and len(data["choices"]) > 0:
                        return data["choices"][0]["message"]["content"].strip()
                    return f"Error: Unexpected response format: {data}"
                except Exception as e:  # noqa: BLE001
                    last_err = str(e)
                    # 4xx（鉴权失败、参数错误）重试没有意义，只会把失败拖长
                    status = getattr(getattr(e, "response", None), "status_code", None)
                    if status is not None and 400 <= status < 500 and status != 429:
                        break
                    if attempt < self.max_retries - 1:
                        time.sleep(1.5 * (attempt + 1))
            return f"Error calling LLM for {self.name}: {last_err}"
        except Exception as e:  # noqa: BLE001
            return f"Error calling LLM for {self.name}: {str(e)}"
