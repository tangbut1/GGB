import sys
import os
import yaml

# 添加当前目录到环境变量，避免导入报错
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.agents.collect_agent import CollectAgent

def load_config():
    with open("src/config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def test_single_agent():
    print("=== 测试 CollectAgent 独立运行 ===")
    config = load_config()
    agent_config = config.get("agent_llm", {}).get("collect_agent", {})
    
    agent = CollectAgent("TestCollect", agent_config)
    # 不传入真实的 forum_manager，验证非论坛模式下的 logging 输出
    res = agent.run({"keyword": "Apple", "max_results": 10})
    
    print("\n--- CollectAgent 执行结果 ---")
    print(f"Status: {res['status']}")
    print(f"Summary: {res['summary']}")
    print(f"数据条数: {len(res.get('data', {}).get('news', []))}")

if __name__ == "__main__":
    test_single_agent()
