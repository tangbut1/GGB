import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.forum.log_manager import LogManager
from src.forum.monitor import ForumMonitor

def load_config():
    return {
        "agent_llm": {
            "forum_host": {
                "trigger_threshold": 3,
                "api_key": "sk-test",
                "base_url": "http://127.0.0.1:9/v1",
                "model": "test-model",
            }
        }
    }

def test_forum_mechanism():
    print("=== 测试论坛 Monitor 与 Host 触发机制 ===")
    config = load_config()
    
    # 强制将触发阈值设为 3 方便测试
    if "agent_llm" not in config:
        config["agent_llm"] = {}
    if "forum_host" not in config["agent_llm"]:
        config["agent_llm"]["forum_host"] = {}
    config["agent_llm"]["forum_host"]["trigger_threshold"] = 3
    config["agent_llm"]["forum_host"]["api_key"] = "sk-test" # 假key测试逻辑
    
    manager = LogManager("test_task")
    monitor = ForumMonitor(manager, config)
    manager.set_monitor(monitor)

    # Inject mock LLMHost (event-driven monitor creates it lazily)
    from src.forum.llm_host import LLMHost
    mock_host = LLMHost(config["agent_llm"]["forum_host"])
    mock_host.generate_guidance = lambda context: "【总结】：测试 Host 已触发\n【盲区引导】：@TrendAgent 继续验证"
    monitor._llm_host = mock_host
    
    monitor.start()
    print("Monitor 已启动...")
    
    manager.write("CollectAgent", 1, "发现了关于苹果销量的负面新闻。")
    time.sleep(1.5)
    manager.write("SentimentAgent", 1, "市场情绪确实呈现下跌趋势。")
    time.sleep(1.5)
    
    print("当前 Host 指引:", manager.get_latest_host_guidance())
    print("再写入一条，触发 Host...")
    manager.write("TrendAgent", 1, "模型预测接下来会继续震荡。")
    
    # 等待Monitor处理
    time.sleep(3)
    
    print("触发后的 Host 指引:", manager.get_latest_host_guidance())
    assert "测试 Host 已触发" in manager.get_latest_host_guidance()
    
    monitor.stop()
    print("测试结束。")

if __name__ == "__main__":
    test_forum_mechanism()
