import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.forum.monitor import ForumMonitor


class FakeLogManager:
    def __init__(self):
        self.host = ""

    def read_all_lines(self):
        return []

    def get_latest_host_guidance(self):
        return self.host

    def write(self, agent_name, iteration, content):
        if agent_name == "HOST":
            self.host = content


def test_forum_monitor_waits_until_host_guidance_arrives():
    manager = FakeLogManager()
    monitor = ForumMonitor(manager, {"agent_llm": {"forum_host": {}}})

    def write_later():
        time.sleep(0.05)
        manager.write("HOST", 1, "【总结】：已补充盲区")
        monitor.mark_host_guidance_ready()

    threading.Thread(target=write_later).start()

    assert monitor.wait_for_host_guidance(timeout=1.0) == "【总结】：已补充盲区"


def test_forum_monitor_wait_returns_empty_on_timeout():
    manager = FakeLogManager()
    monitor = ForumMonitor(manager, {"agent_llm": {"forum_host": {}}})

    assert monitor.wait_for_host_guidance(timeout=0.01) == ""


if __name__ == "__main__":
    test_forum_monitor_waits_until_host_guidance_arrives()
    test_forum_monitor_wait_returns_empty_on_timeout()
