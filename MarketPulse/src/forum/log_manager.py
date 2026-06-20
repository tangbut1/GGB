import os
import threading
from pathlib import Path
from datetime import datetime

class LogManager:
    def __init__(self, task_id: str, log_dir: str = None):
        self.task_id = task_id
        self.log_dir = log_dir or str(Path(__file__).parent.parent.parent / "logs")
        self.log_file = os.path.join(self.log_dir, f"forum_{task_id}.log")
        self.lock = threading.Lock()
        self.latest_host_msg = ""
        self.messages = []  # Structured message history
        self.usage_stats = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "prompt_cache_hit_tokens": 0,
            "prompt_cache_miss_tokens": 0,
            "total_tokens": 0
        }
        
        os.makedirs(self.log_dir, exist_ok=True)
        # 确保初始为空
        with open(self.log_file, "w", encoding="utf-8") as f:
            f.write(f"--- Forum Log Started for Task: {task_id} ---\n")
            
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
