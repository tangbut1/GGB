# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Entry Points

- **`MarketPulse/console.py`** — Textual TUI console workstation (primary). Start with `PYTHONPATH=. python3 console.py`. Multi-agent forum analysis with real-time agent status, live forum stream, causal chains, follow-up Q&A modal.
- **`MarketPulse/main.py`** — Streamlit standalone dashboard (secondary, for local Agent testing). `streamlit run main.py`.

These two entry points are **completely independent**. `main.py` does not use the multi-agent forum architecture — it calls `src/` modules directly via the older pipeline (NewsCollector → DataCleaner → SentimentAnalyzer → TrendPredictor). `console.py` is the real system.

## Commands

```bash
# Install
pip install -r requirements.txt
cp .env.example .env   # then edit with real API keys

# Run TUI console workstation
cd MarketPulse && PYTHONPATH=. python3 console.py

# Run Streamlit dashboard
streamlit run main.py

# Run individual tests (must run from MarketPulse/ directory)
python3 tests/test_agents.py      # CollectAgent standalone
python3 tests/test_forum.py       # Forum Monitor + Host trigger mechanism
```

## Architecture: Multi-Agent Forum System

Five agents plus an orchestrator and a forum monitor, inspired by the BettaFish architecture pattern.

### Agents (extend `BaseAgent`)

Each agent has `run(input_data) → {status, data, summary}` and calls LLM via `call_llm(prompt)` or `call_llm_with_system(sys, usr)`. All use OpenAI-compatible API (configurable per-agent).

| Agent | Role | Key dependency |
|---|---|---|
| `CollectAgent` | Multi-source search (Google RSS → DDG → Bing) + local data merge | `custom_search.py`, `DataCleaner` |
| `SentimentAgent` | SnowNLP scoring + LLM校正 (corrects SnowNLP's positive bias on Chinese financial text) | `SentimentAnalyzer` |
| `TrendAgent` | Prophet time-series prediction + data quality rating | `TrendPredictor` |
| `ReportAgent` | AI insights JSON + forum debate extraction + event graph | `export_html.py`, `EventExtractor` |
| `LLMHost` | Forum moderator — summarizes agent findings, identifies blind spots, guides next round | Called by `ForumMonitor` |

### Pipeline (`OrchestratorAgent`)

Two modes:
- **`stream_pipeline()`** — generator yielding `PipelineEvent` / `ForumEvent` / `ReportEvent` / `ErrorEvent`. Used by TUI via `run_worker(thread=True)`.
- **`run_pipeline()`** — blocking call returning dict. Used by scripts or headless automation.

```
Collect → Sentiment → Trend → [wait Monitor triggers Host] → optional Round 2 (if Host feedback) → Report (event graph + causal chains)
```

- Trend failure is **non-fatal** — injects degraded fallback summary so downstream stages still get data.
- If no real search results, CollectAgent returns an error (no mock data).

### Forum Mechanism

- **`LogManager`**: Thread-safe file append to `logs/forum_{task_id}.log`. Every agent writes findings here. Calls `monitor.on_message_written()` on each write — **event-driven**, no polling.
- **`ForumMonitor`**: Uses `threading.Condition` for idle-timeout detection. Triggers Host LLM when ≥5 agent messages or 10s idle since last message.
- **Host guidance** is written back to the forum log and read by the orchestrator for Round 2 iteration.

### TUI (`console.py`)

Textual-based console workstation with 3 screens:
- **MainScreen**: Split layout — agent status panel (left), forum live stream + insights/causal chains (right), keyword input, progress header
- **FollowupModal** (`Q` key): Streaming LLM Q&A with current analysis context
- **HistoryScreen** (`H` key): Browse past tasks from TaskStore, view reports/graphs, re-run analyses

Thread model: Orchestrator runs in `run_worker(thread=True)` worker thread, posts events to UI thread via `call_from_thread()`.

### Configuration Hierarchy (env vars override config.yaml)

```
MP_{AGENT}_MODEL / MP_{AGENT}_BASE_URL   (per-agent, highest)
  → MP_GLOBAL_MODEL / MP_GLOBAL_BASE_URL  (global)
    → config.yaml defaults                 (lowest)
```

Each of the 5 agents + forum_host gets its own API key via `MP_{COLLECT|SENTIMENT|TREND|REPORT|FORUM_HOST}_AGENT_API_KEY`.

### Visualization

- **Event Graph**: LLM-based SPO triple extraction (`EventExtractor._extract_with_llm()`) with jieba co-occurrence fallback. pyvis renders standalone HTML with color-coded edges (red=causal, blue=temporal, orange=adversarial).
- **Causal Chains**: Terminal-formatted top-5 causal paths from graph topology (`visualization/causal_chain.py`).

## Key Patterns

- **All LLM calls** go through `BaseAgent._call_llm_inner()` → OpenAI-compatible `/chat/completions` endpoint, 60s timeout, no retry.
- **JSON extraction from LLM responses** uses 4-level fallback: direct parse → strip code fences → find `{...}` slice → regex match. The ReportAgent adds a 5th level: Markdown structure parsing when JSON is entirely absent.
- **Sentiment correction**: SnowNLP systematically under-reports negative sentiment for Chinese financial/political text. SentimentAgent sends SnowNLP results + samples to LLM for correction, then applies label redistribution sorted by score.
- **`src/config.yaml`** uses `${ENV_VAR}` placeholders expanded at startup by `_expand_env()` in `config.py`.
- The `data/` directory caches search results; `results/reports/` holds generated HTML reports and graph files.
