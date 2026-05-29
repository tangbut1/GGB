import threading
from .. import config as cfg


class ForumMonitor:
    """Event-driven forum monitor.

    LogManager.write() → Monitor.on_message_written() → check threshold
    → trigger Host LLM in background thread.

    Idle timeout is handled via Condition.wait() instead of sleep-polling.
    The daemon thread still exists for idle-timeout detection, but it no
    longer reads files — it purely waits on a condition variable.
    """

    def __init__(self, log_manager, config: dict):
        self.log_manager = log_manager
        self.config = config
        forum_cfg = config.get("agent_llm", {}).get("forum_host", {})
        self.trigger_threshold = forum_cfg.get("trigger_threshold", cfg.forum_trigger_threshold())
        self.running = False
        self.thread = None

        # Event-driven state
        self._agent_msg_count = 0
        self._condition = threading.Condition()
        self.host_guidance_event = threading.Event()

        # LLM Host (created once, lazy)
        self._llm_host = None

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._idle_timeout_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        with self._condition:
            self._condition.notify_all()
        if self.thread:
            self.thread.join(timeout=1.0)

    def on_message_written(self, agent_name: str):
        """Called by LogManager.write() on every log append (event-driven)."""
        if agent_name in ("HOST", "SYSTEM"):
            return

        with self._condition:
            self._agent_msg_count += 1
            if self._agent_msg_count >= self.trigger_threshold:
                self._agent_msg_count = 0
                # Trigger Host in background thread
                threading.Thread(target=self._trigger_host, daemon=True).start()
            self._condition.notify_all()

    def mark_host_guidance_ready(self):
        self.host_guidance_event.set()

    def wait_for_host_guidance(self, timeout: float = 15.0) -> str:
        skip = ("【HOST错误】", "【HOST提示】", "[LLM不可用]")
        existing = self.log_manager.get_latest_host_guidance()
        if existing and not any(existing.startswith(m) for m in skip):
            return existing
        if self.host_guidance_event.wait(timeout=timeout):
            result = self.log_manager.get_latest_host_guidance()
            if result and not any(result.startswith(m) for m in skip):
                return result
        return ""

    def _idle_timeout_loop(self):
        """Daemon thread: wake on notification or idle timeout to trigger Host."""
        while self.running:
            with self._condition:
                # Wait up to 10s for new messages
                self._condition.wait(timeout=10)
                if not self.running:
                    return
                # Idle timeout: any pending messages after 10s silence
                if self._agent_msg_count > 0:
                    self._agent_msg_count = 0
                    threading.Thread(target=self._trigger_host, daemon=True).start()

    def _trigger_host(self):
        """Read recent log lines and ask Host LLM to generate guidance."""
        if self._llm_host is None:
            from .llm_host import LLMHost
            forum_cfg = self.config.get("agent_llm", {}).get("forum_host", {})
            self._llm_host = LLMHost(forum_cfg)

        lines = self.log_manager.read_all_lines()
        context = "".join(lines[-20:])
        summary = self._llm_host.generate_guidance(context)

        if summary:
            skip_markers = ("【HOST错误】", "【HOST提示】", "[LLM不可用]")
            if not any(summary.startswith(m) for m in skip_markers):
                self.log_manager.write("HOST", 1, summary)
            self.mark_host_guidance_ready()
