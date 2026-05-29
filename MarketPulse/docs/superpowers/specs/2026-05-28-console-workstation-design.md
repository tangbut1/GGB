# MarketPulse Console Workstation — Design Spec

## Summary

Transform MarketPulse from a Flask+SocketIO web app (3100-line single HTML frontend, fake progress bars, brittle SocketIO state) into a professional Textual TUI console workstation. Delete all mock/fake data. Rewrite the event graph extraction to use LLM-based causal triple extraction.

## Architecture

```
console.py                  # New entry point
  └── src/cli/app.py        # Textual App
        ├── screens/
        │   ├── main.py     # Primary split-screen monitor
        │   └── history.py  # Past task browser
        └── widgets/
            ├── agent_panel.py    # Left sidebar — agent status
            ├── forum_panel.py    # Center-top — live debate stream
            ├── insight_panel.py  # Center-bottom — AI insights + causal chains
            └── header.py         # Progress bar + keyword + timer

src/agents/orchestrator.py  # Refactored: socketio.emit → yield PipelineEvent
src/analysis/event_extractor.py  # Rewritten: jieba co-occur → LLM triples
src/visualization/
  ├── graph_renderer.py     # pyvis standalone HTML export
  └── causal_chain.py       # Terminal text causal chain formatter
src/cli/events.py           # Event dataclasses (PipelineEvent, ForumEvent, ReportEvent)
```

## Thread Model

- Textual main thread runs asyncio event loop — widgets, rendering, keyboard input
- Orchestrator runs in a worker thread (`app.run_worker(..., thread=True)`)
- Orchestrator yields events → worker callback calls `self.post_message(event)` → UI thread consumes via `@on(EventType)` handlers
- Cancel: store Worker reference, call `worker.cancel()` → orchestrator checks token between phases
- Agents remain synchronous — no asyncio conversion needed

## TUI Layout

```
┌──────────────┬──────────────────────────────────────┐
│  MarketPulse            小米汽车          [00:42]   │  ← Header (progress + keyword + timer)
│  ████████████░░░░░░░░░ 65%  趋势预测中...           │
├──────────────┼──────────────────────────────────────┤
│ Agents       │ Forum Live                            │
│              │ [CollectAgent R1] 采集到 23 条数据    │
│ ● CollectAgent│ [SentimentAgent R1] 正面 45% 负面 32%│
│ ● SentimentAg│ [HOST R1] 建议关注供应链相关新闻      │
│ ◌ TrendAgent │ [TrendAgent R1] 预测趋势向上, 置信度  │
│ ○ ReportAgent│                                        │
│              ├──────────────────────────────────────┤
│ Status: Done │ Insights / Causal Chains              │
│              │ 小米汽车产能扩张 → 供应链紧张 →        │
│ Config:      │   交付延迟风险 [因果, 0.87]            │
│ 3/4 API Keys│ 价格战加剧 → 利润率压缩 [因果, 0.72]   │
│              │                                        │
│              │ [Q] 追问  [G] 打开图谱  [R] 查看报告   │
└──────────────┴──────────────────────────────────────┘
```

Footer shows keybindings: Q=followup, G=open graph HTML, R=view report, Ctrl+C=quit

## Data Flow

1. User types keyword → Textual App creates OrchestratorAgent
2. `run_worker(orchestrator.run_pipeline, thread=True)` starts
3. Each phase yields `PipelineEvent` → `post_message()` → widget updates
4. Forum log writes go through `LogManager` as before, but also yield `ForumEvent`
5. ReportAgent produces structured JSON, no HTML
6. `graph_renderer.py` takes nodes/edges, produces standalone HTML via pyvis
7. `causal_chain.py` formats top-K causal paths as terminal text
8. Final result cached to `results/reports/{task_id}.json`

## Event Graph Rewrite

Current: jieba TF-IDF keyword extraction → co-occurrence edges. No LLM, no causal reasoning.

New: feed analyzed_news to LLM with prompt:
- Extract strict SPO triples: (Subject, Predicate, Object)
- Classify each edge: causal | temporal | adversarial
- Assign confidence 0-1
- pyvis renders with color-coded edges (red=causal, blue=temporal, orange=adversarial)
- Top-5 causal chains printed as terminal text

## Fake Data Removal

- `collect_agent.py:120-150`: DELETE — mock news items. If search fails, fail gracefully.
- `templates/index.html:1549-1597`: DELETE — entire fake progress timer. Replaced by real Textual progress.
- `templates/index.html:1897-1902`: DELETE — backend timeout fallback to "frontend simulation mode."
- `templates/index.html:2135`: DELETE — offline mode simulated data fallback.
- `report_agent.py:47-56`: KEEP — rule-based fallback when LLM unavailable. Not fake data, it's graceful degradation.

## Migration Strategy

1. Create `src/cli/` with Textual app — new code, no impact on existing
2. Create `console.py` entry point
3. Refactor orchestrator to generator pattern — backward compat via adapter
4. Rewrite event_extractor.py
5. Create `src/visualization/`
6. Delete fake data
7. Final: optionally remove `templates/index.html` and Flask deps from `app.py`

`app.py` stays functional during development. `console.py` is the new primary entry point.
