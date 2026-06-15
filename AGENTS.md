# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Entry Points

- **`MarketPulse/src/cli/app.py`** — Textual TUI 工作台主入口 (primary)。Start with `python3 console.py` or `python -m src.cli.app`。通过事件流（`PipelineEvent`, `ReportEvent`等）解耦 UI 与内核，支持交互式仪表盘、流式日志。
- **`MarketPulse/main.py`** — Streamlit standalone dashboard (secondary, for local Agent testing). `streamlit run main.py`.

These two entry points are **completely independent**. `main.py` does not use the multi-agent forum architecture — it calls `src/` modules directly via the older pipeline. `src/cli/app.py` is the real system (replaces the older Flask `app.py`).

## Commands

```bash
# Install
pip install -r requirements.txt
cp .env.example .env   # then edit with real API keys

# Run TUI workspace
python3 console.py
# or: python -m src.cli.app

# Run headless (no TUI)
python -m src.cli.app -k "华为" -m news

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
| `ReportAgent` | HTML report generation + AI insights JSON + forum debate extraction | `export_html.py`, `EventExtractor` |
| `LLMHost` | Forum moderator — summarizes agent findings, identifies blind spots, guides next round | Called by `ForumMonitor` |

### Pipeline (`OrchestratorAgent.run_pipeline()`)

```
Collect → Sentiment → Trend → [wait Monitor triggers Host] → optional Round 2 (if Host feedback) → Report (HTML + event graph)
```

- Trend failure is **non-fatal** — injects degraded fallback summary so downstream stages still get data.
- If no real search results, CollectAgent **fast-fails** with a clear error (no mock data injection).

### Forum Mechanism

- **`LogManager`**: Thread-safe file append to `logs/forum_{task_id}.log`. Every agent writes findings here.
- **`ForumMonitor`**: Daemon thread polls log, counts non-HOST/non-SYSTEM messages. Triggers Host LLM when ≥5 agent messages or 10s idle since last message.
- **Host guidance** is written back to the forum log and read by the orchestrator for Round 2 iteration.

### Configuration Hierarchy (env vars override config.yaml)

```
MP_{AGENT}_MODEL / MP_{AGENT}_BASE_URL   (per-agent, highest)
  → MP_GLOBAL_MODEL / MP_GLOBAL_BASE_URL  (global)
    → config.yaml defaults                 (lowest)
```

Each of the 5 agents + forum_host gets its own API key via `MP_{COLLECT|SENTIMENT|TREND|REPORT|FORUM_HOST}_AGENT_API_KEY`.

### Frontend (TUI)

Textual based terminal application (`src/cli/app.py`). Left panel: console log and task history list. Right panel: interactive tabs — Pipeline/Forum Log, Agent Report (Insights), Graph View (textual causal chains). Async generators push agent status updates and log lines in real time through events (`src/cli/events.py`).

## Key Patterns

- **All LLM calls** go through `BaseAgent._call_llm_inner()` → shared `LLMClient` (connection-pooled `requests.Session`) → OpenAI-compatible `/chat/completions` endpoint. Per-agent timeout and retry count are configured in `config.yaml` (`timeout` / `max_retries` fields); defaults are resolved via `src/config.py`.
- **JSON extraction from LLM responses** uses 5-level fallback: strip code fences → direct parse → find `{...}` slice → regex match → Markdown structure parsing.
- **Sentiment correction**: SnowNLP systematically under-reports negative sentiment for Chinese financial/political text. SentimentAgent sends SnowNLP results + samples to LLM for correction, then applies label redistribution sorted by score.
- **`src/config.yaml`** uses `${ENV_VAR}` placeholders expanded at startup by `src/config.py`.
- The `data/` directory caches search results; `results/reports/` holds generated HTML reports.
