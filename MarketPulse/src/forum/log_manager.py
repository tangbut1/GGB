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
        
        os.makedirs(self.log_dir, exist_ok=True)
        # 确保初始为空
        with open(self.log_file, "w", encoding="utf-8") as f:
            f.write(f"--- Forum Log Started for Task: {task_id} ---\n")
            
    def write(self, agent_name: str, iteration: int, content: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] [{agent_name}] [Round {iteration}] {content}\n"
        
        with self.lock:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(log_line)
            if agent_name == "HOST":
                self.latest_host_msg = content

    def get_latest_host_guidance(self) -> str:
        with self.lock:
            return self.latest_host_msg
            
    def read_all_lines(self) -> list:
        with self.lock:
            if not os.path.exists(self.log_file):
                return []
            with open(self.log_file, "r", encoding="utf-8") as f:
                return f.readlines()
