import time
import threading
from .llm_host import LLMHost

class ForumMonitor:
    def __init__(self, log_manager, config: dict):
        self.log_manager = log_manager
        self.config = config
        self.llm_host = LLMHost(config.get("agent_llm", {}).get("forum_host", {}))
        self.running = False
        self.thread = None
        self.trigger_threshold = config.get("agent_llm", {}).get("forum_host", {}).get("trigger_threshold", 5)
        
    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
            
    def _monitor_loop(self):
        last_processed_line = 0
        agent_msg_count = 0
        last_msg_time = time.time()
        
        while self.running:
            lines = self.log_manager.read_all_lines()
            new_lines = lines[last_processed_line:]
            
            if new_lines:
                for line in new_lines:
                    if "[HOST]" not in line and "[SYSTEM]" not in line and "--- Forum" not in line:
                        agent_msg_count += 1
                        last_msg_time = time.time()
                last_processed_line = len(lines)
                
            time_since_last_msg = time.time() - last_msg_time
            
            # 触发条件：消息大于阈值，或者消息>0且距离上一次有一段时间
            if agent_msg_count >= self.trigger_threshold or (agent_msg_count > 0 and time_since_last_msg > 10):
                # 子线程异步调用，避免 HTTP 请求阻塞 Monitor 主循环导致日志推送卡顿
                                threading.Thread(target=self._trigger_host, args=(self.log_manager.get_all_messages(),), daemon=True).start()
                agent_msg_count = 0
                
            time.sleep(1)
            
        def _trigger_host(self, forum_messages: list):
                recent_messages = forum_messages[-20:]  # 截取最近20条结构化消息
                summary = self.llm_host.generate_guidance(recent_messages)
        if summary:
            self.log_manager.write("HOST", 1, summary)
