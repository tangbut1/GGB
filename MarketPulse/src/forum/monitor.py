import threading
import time

from .llm_host import LLMHost


class ForumMonitor:
    """Watches the forum log and triggers the Host LLM when the debate goes quiet.

    Two trigger paths:
    - agent message count reaches ``trigger_threshold``, or
    - ``idle_timeout`` seconds pass with no new agent message.

    The pipeline can also block on ``wait_for_host_guidance()`` until the host
    has spoken (signalled via ``mark_host_guidance_ready()``).
    """

    def __init__(self, log_manager, config: dict):
        self.log_manager = log_manager
        self.config = config
        host_cfg = config.get("agent_llm", {}).get("forum_host", {})
        self._llm_host = LLMHost(host_cfg)
        self.running = False
        self.thread = None
        self.trigger_threshold = host_cfg.get("trigger_threshold", 5)
        self.idle_timeout = host_cfg.get("idle_timeout", 10)

        self._cond = threading.Condition()
        self._host_guidance = ""
        self._host_ready = False

    # ── lifecycle ────────────────────────────────────────────────────
    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
            self.thread = None

    # ── host guidance signalling ─────────────────────────────────────
    def mark_host_guidance_ready(self):
        """Signal waiters that new host guidance is available."""
        with self._cond:
            self._host_ready = True
            self._cond.notify_all()

    def wait_for_host_guidance(self, timeout: float = 10.0) -> str:
        """Block until the host has spoken or ``timeout`` elapses."""
        deadline = time.time() + timeout
        with self._cond:
            while not self._host_ready:
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                self._cond.wait(remaining)
            if self._host_ready:
                self._host_ready = False  # 一次性信号，消费后复位
                return self.log_manager.get_latest_host_guidance()
            return ""

    # ── event-driven hook (called by LogManager on every write) ──────
    def on_message_written(self):
        """No-op hook kept for the event-driven LogManager contract."""
        return

    # ── polling loop ─────────────────────────────────────────────────
    def _monitor_loop(self):
        last_processed_line = 0
        agent_msg_count = 0
        last_msg_time = time.time()

        while self.running:
            try:
                lines = self.log_manager.read_all_lines()
            except Exception:
                lines = []
            new_lines = lines[last_processed_line:]

            if new_lines:
                for line in new_lines:
                    if "[HOST]" not in line and "[SYSTEM]" not in line and "--- Forum" not in line:
                        agent_msg_count += 1
                        last_msg_time = time.time()
                last_processed_line = len(lines)

            time_since_last_msg = time.time() - last_msg_time

            # 触发条件：消息大于阈值，或者消息>0且空闲超过 idle_timeout
            if agent_msg_count >= self.trigger_threshold or (
                agent_msg_count > 0 and time_since_last_msg > self.idle_timeout
            ):
                # 子线程异步调用，避免 HTTP 请求阻塞 Monitor 主循环导致日志推送卡顿
                threading.Thread(
                    target=self._trigger_host,
                    args=(self.log_manager.get_all_messages(),),
                    daemon=True,
                ).start()
                agent_msg_count = 0

            time.sleep(1)

    def _trigger_host(self, forum_messages: list):
        try:
            guidance = self._llm_host.generate_guidance(forum_messages)
        except Exception as e:
            guidance = f"【HOST错误】：{e}"
        if guidance and "【HOST错误】" not in guidance:
            self.log_manager.write("HOST", 1, guidance)
            self.mark_host_guidance_ready()
