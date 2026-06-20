from src.agents.orchestrator import OrchestratorAgent
orch = OrchestratorAgent("task_test")
res = orch.run_pipeline()
print("Pipeline Result:", res)
