import os
import threading
from pathlib import Path
from datetime import datetime

from ..net_safety import safe_output_path

class LogManager:
    def __init__(self, task_id: str, log_dir: str = None):
        self.task_id = task_id
        self.log_dir = log_dir or str(Path(__file__).parent.parent.parent / "logs")
        # task_id 由调用方给出，拼进文件名这一步不能靠"上游恰好安全"来保证。
        # 以 log_dir 为基准收敛：分量含分隔符、是绝对路径或拼完越界，一律拒绝。
        self.log_file = str(safe_output_path(self.log_dir, f"forum_{task_id}.log"))
        self.lock = threading.Lock()
        self.latest_host_msg = ""
        self.messages = []  # Structured message history
        self.monitor = None
        self.usage_stats = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "prompt_cache_hit_tokens": 0,
            "prompt_cache_miss_tokens": 0,
            "total_tokens": 0
        }
        
        os.makedirs(self.log_dir, exist_ok=True)
        # 确保初始为空
        Path(self.log_file).write_text(
            f"--- Forum Log Started for Task: {task_id} ---\n",
            encoding="utf-8")
            
    def set_monitor(self, monitor) -> None:
        """Attach the ForumMonitor so writes can notify it (event-driven)."""
        self.monitor = monitor

    def write(self, agent_name: str, iteration: int, content: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Append to structured memory
        msg_obj = {
            "timestamp": timestamp,
            "agent": agent_name,
            "round": iteration,
            "content": content
        }

        with self.lock:
            self.messages.append(msg_obj)

            # Still write to flat log file for debugging
            log_line = f"[{timestamp}] [{agent_name}] [Round {iteration}] {content}\n"
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(log_line)

            if agent_name == "HOST":
                self.latest_host_msg = content

        # 锁外通知，避免与 monitor 的锁顺序互锁
        if self.monitor is not None:
            try:
                self.monitor.on_message_written()
            except Exception:
                pass

    def get_all_messages(self) -> list:
        """返回所有结构化消息"""
        with self.lock:
            return list(self.messages)

    def get_latest_host_guidance(self) -> str:
        with self.lock:
            return self.latest_host_msg
            
    def add_usage(self, usage: dict):
        """累加 LLM 返回的 token 消耗统计"""
        with self.lock:
            self.usage_stats["prompt_tokens"] += usage.get("prompt_tokens", 0)
            self.usage_stats["completion_tokens"] += usage.get("completion_tokens", 0)
            self.usage_stats["total_tokens"] += usage.get("total_tokens", 0)
            
            # DeepSeek 特定缓存命中字段
            self.usage_stats["prompt_cache_hit_tokens"] += usage.get("prompt_cache_hit_tokens", 0)
            self.usage_stats["prompt_cache_miss_tokens"] += usage.get("prompt_cache_miss_tokens", 0)
            
    def get_usage_stats(self) -> dict:
        """返回当前的缓存统计数据"""
        with self.lock:
            return dict(self.usage_stats)
            
    def read_all_lines(self) -> list:
        with self.lock:
            if not os.path.exists(self.log_file):
                return []
            with open(self.log_file, "r", encoding="utf-8") as f:
                return f.readlines()
