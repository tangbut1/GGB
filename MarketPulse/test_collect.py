from src.agents.collect_agent import CollectAgent
class MockForum:
    def write(self, *args):
        print("Forum:", args)
agent = CollectAgent("CollectAgent", {}, MockForum())
res = agent.run({"keyword": "美加墨世界杯", "src_mode": "news"})
print("Result:", res["status"])
