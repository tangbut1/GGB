"""Follow-up Q&A modal screen."""

from textual.screen import ModalScreen
from textual.app import ComposeResult
from textual.widgets import Input, Static
from textual.containers import Container, VerticalScroll


class FollowupModal(ModalScreen):
    """Modal that lets the user ask a follow-up question about the analysis."""

    CSS = """
    FollowupModal {
        align: center middle;
    }

    #followup-dialog {
        width: 70%;
        max-width: 90;
        height: auto;
        max-height: 80%;
        background: #161b22;
        border: solid #30363d;
        padding: 1 2;
    }

    #followup-title {
        color: #58a6ff;
        text-style: bold;
        padding: 1 0;
    }

    #followup-context {
        color: #8b949e;
        padding: 0 0 1 0;
        text-style: italic;
    }

    #followup-input {
        margin: 1 0;
    }

    #followup-response {
        height: auto;
        max-height: 12;
        margin-top: 1;
        padding: 1;
        background: #0d1117;
        border: solid #21262d;
        color: #c9d1d9;
    }

    #followup-spinner {
        color: #d2991d;
        text-style: bold;
        padding: 1 0;
    }

    #followup-footer {
        color: #484f58;
        padding: 1 0 0 0;
        text-style: italic;
    }

    Input {
        background: #0d1117;
        color: #c9d1d9;
        border: solid #30363d;
    }

    Input:focus {
        border: solid #58a6ff;
    }
    """

    def __init__(self, keyword: str, conclusion: str, llm_config: dict):
        super().__init__()
        self._keyword = keyword
        self._conclusion = conclusion
        self._llm_config = llm_config
        self._full_response = ""

    def compose(self) -> ComposeResult:
        with Container(id="followup-dialog"):
            yield Static(f"追问分析: [bold cyan]{self._keyword}[/bold cyan]", id="followup-title")
            yield Static(
                f"当前结论: {self._conclusion[:120]}{'...' if len(self._conclusion) > 120 else ''}",
                id="followup-context"
            )
            yield Input(placeholder="输入你的追问...（Enter 发送，Esc 关闭）", id="followup-input")
            yield Static("", id="followup-spinner")
            with VerticalScroll(id="followup-response"):
                yield Static("", id="followup-response-text")
            yield Static("Esc 关闭  │  Enter 发送", id="followup-footer")

    def on_mount(self):
        self.query_one("#followup-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        question = event.value.strip()
        if not question:
            return

        inp = self.query_one("#followup-input", Input)
        inp.disabled = True
        response_widget = self.query_one("#followup-response-text", Static)
        spinner = self.query_one("#followup-spinner", Static)
        spinner.update("⏳ AI 分析中...")
        self._full_response = ""

        # Run LLM call in worker thread
        self.run_worker(
            self._call_followup_llm(question, response_widget, spinner, inp),
            thread=True,
            exclusive=True,
        )

    def _call_followup_llm(self, question: str, response_widget: Static, spinner: Static, inp: Input):
        """Call LLM for follow-up and stream response chunks to the modal."""
        import requests
        import json as _json

        cfg = self._llm_config
        base_url = cfg.get("base_url", "").rstrip("/")
        if not base_url.endswith("/chat/completions"):
            base_url = f"{base_url}/chat/completions"
        api_key = cfg.get("api_key", "")
        model = cfg.get("model", "gpt-3.5-turbo")

        if not api_key:
            self.call_from_thread(response_widget.update, "❌ API Key 未配置，请在 .env 中设置。")
            self.call_from_thread(spinner.update, "")
            self.call_from_thread(lambda: setattr(inp, "disabled", False))
            return

        system_prompt = (
            "你是一名顶级对冲基金的首席舆情分析师，正在回答用户对分析的追问。"
            "回答简洁有力，不超过150字，直接给出答案不废话。"
            "如果问题涉及投资建议，请声明风险提示。"
        )

        user_prompt = (
            f"关键词: {self._keyword}\n"
            f"分析结论: {self._conclusion}\n"
            f"用户追问: {question}\n\n"
            "请基于以上信息回答用户的追问。"
        )

        try:
            endpoint = base_url
            resp = requests.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.7,
                    "stream": True,
                },
                timeout=60,
                stream=True,
            )
            resp.raise_for_status()

            for line in resp.iter_lines():
                if not line:
                    continue
                line_str = line.decode("utf-8")
                if line_str.startswith("data: "):
                    chunk_data = line_str[6:]
                    if chunk_data == "[DONE]":
                        break
                    try:
                        chunk_json = _json.loads(chunk_data)
                        delta = chunk_json.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            self._full_response += content
                            self.call_from_thread(
                                response_widget.update, self._full_response
                            )
                    except _json.JSONDecodeError:
                        pass

            if not self._full_response:
                self.call_from_thread(response_widget.update, "(AI 未返回内容，请重试)")

        except Exception as e:
            self.call_from_thread(response_widget.update, f"❌ 请求失败: {str(e)}")

        finally:
            self.call_from_thread(spinner.update, "")
            self.call_from_thread(lambda: setattr(inp, "disabled", False))
            self.call_from_thread(lambda: inp.focus())

    def key_escape(self):
        self.dismiss()
