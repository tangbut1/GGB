import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.collect_agent import CollectAgent
import src.agents.collect_agent as collect_agent_module

def load_config():
    return {"agent_llm": {"collect_agent": {"api_key": "", "model": "test-model"}}}


class FakeSourceAwareCollector:
    def __init__(self):
        self.sources = []

    def run_custom_search(self, keyword, max_results=120):
        return [
            {
                "title": f"{keyword} 测试新闻",
                "summary": "测试摘要",
                "url": "https://example.com/news",
                "link": "https://example.com/news",
                "source": "测试源",
                "publish_time": "2026-05-23 09:30",
                "source_refs": ["src_test"],
                "source_ref": {"source_id": "src_test", "title": f"{keyword} 测试新闻"},
                "content_hash": "testhash",
            }
        ]

def test_single_agent():
    print("=== 测试 CollectAgent 独立运行 ===")
    config = load_config()
    agent_config = config.get("agent_llm", {}).get("collect_agent", {})
    collect_agent_module.SourceAwareCollector = FakeSourceAwareCollector
    
    agent = CollectAgent("TestCollect", agent_config)
    # 不传入真实的 forum_manager，验证非论坛模式下的 logging 输出
    res = agent.run({"keyword": "Apple", "max_results": 10})
    
    print("\n--- CollectAgent 执行结果 ---")
    print(f"Status: {res['status']}")
    print(f"Summary: {res['summary']}")
    print(f"数据条数: {len(res.get('data', {}).get('news', []))}")

if __name__ == "__main__":
    test_single_agent()
